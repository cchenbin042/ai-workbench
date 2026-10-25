"""Windows path validation and guarded file reads for approved directories.

Every read is bounded by a grant: either an approved directory root (segment
containment, case-insensitive) or an exact file list from the dialog. Reparse
points are rejected on every component, and the read re-verifies identity,
stat, and the real path target before returning a snapshot.
"""
import codecs
import hashlib
import os
import re
import stat as stat_module
from pathlib import Path, PureWindowsPath

from .contracts import DomainError

MAX_SINGLE_FILE_BYTES = 200_000
_REPARSE_FLAG = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DRIVE = re.compile(r"[A-Za-z]:")
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{index}" for index in range(1, 10)),
             *(f"LPT{index}" for index in range(1, 10))}

ALLOWED_ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "gb18030", "gbk", "big5",
                     "shift_jis", "cp1252", "latin-1")


def _drive_letter(path: PureWindowsPath) -> bool:
    return _DRIVE.fullmatch(path.drive) is not None


def normalize_absolute_path(raw: str) -> Path:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise DomainError("PATH_INVALID", "That path is not a usable Windows path")
    if raw.startswith(("\\\\", "//")):
        raise DomainError("PATH_INVALID", "UNC and device paths are not supported")
    candidate = PureWindowsPath(raw)
    if not _drive_letter(candidate):
        raise DomainError("PATH_INVALID", "Only local drive-letter paths are supported")
    tail = raw[2:]
    if ":" in tail:
        # A second colon can only be an NTFS alternate data stream here.
        raise DomainError("PATH_INVALID", "Alternate data streams are not supported")
    resolved = Path(os.path.realpath(raw))
    # realpath may have walked through a junction onto a UNC share or device path.
    if str(resolved).startswith(("\\\\", "//")) or not _drive_letter(PureWindowsPath(resolved)):
        raise DomainError("PATH_INVALID", "The target resolves outside local drives")
    for part in resolved.parts[1:]:
        stem = part.split(".", 1)[0].upper()
        if stem in _RESERVED:
            raise DomainError("PATH_INVALID", "Reserved device names are not supported")
    return resolved


def casefolded_parts(path: Path) -> list[str]:
    return [part.casefold() for part in path.parts]


def ensure_within_root(root: Path, target: Path) -> None:
    root_parts = casefolded_parts(root)
    target_parts = casefolded_parts(target)
    if len(target_parts) <= len(root_parts) or target_parts[:len(root_parts)] != root_parts:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "The selected file is outside the approved directory")


def relative_parts_under(root: Path, target: Path) -> PureWindowsPath:
    ensure_within_root(root, target)
    return PureWindowsPath(*target.parts[len(root.parts):])


def _reject_reparse(path: Path, missing_code: str) -> None:
    try:
        info = os.lstat(path)
    except OSError:
        raise DomainError(missing_code, "The selected file is no longer available") from None
    if getattr(info, "st_file_attributes", 0) & _REPARSE_FLAG:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "Links and reparse points are not supported")


def ensure_no_reparse_components(root: Path, relative: PureWindowsPath) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        _reject_reparse(current, "SOURCE_CHANGED")


def validate_relative_entry(entry: str) -> PureWindowsPath:
    if not entry or "\x00" in entry or ":" in entry:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "The selected file is outside the approved directory")
    candidate = PureWindowsPath(entry)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "The selected file is outside the approved directory")
    parts = candidate.parts
    if any(part in {"..", "."} for part in parts):
        raise DomainError("SOURCE_OUT_OF_SCOPE", "The selected file is outside the approved directory")
    for part in parts:
        stem = part.split(".", 1)[0].upper()
        if stem in _RESERVED:
            raise DomainError("SOURCE_OUT_OF_SCOPE", "Reserved device names are not supported")
    if len(parts) > 24:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "The selected file is nested too deeply")
    return candidate


def _decode(data: bytes, override: str | None) -> tuple[str, str]:
    if override is not None:
        if override not in ALLOWED_ENCODINGS:
            raise DomainError("SOURCE_DECODE_FAILED", "That encoding is not offered")
        try:
            return data.decode(override), override
        except UnicodeDecodeError:
            raise DomainError("SOURCE_DECODE_FAILED",
                              "The file does not decode with the selected encoding") from None
    if data.startswith(codecs.BOM_UTF8):
        try:
            return data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            raise DomainError("SOURCE_DECODE_FAILED", "The file is not valid UTF-8 text") from None
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            raise DomainError("SOURCE_DECODE_FAILED", "The file is not valid UTF-16 text") from None
    if b"\x00" in data[:8192]:
        raise DomainError("SOURCE_DECODE_FAILED",
                          "The file looks binary; text materials must be plain text")
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        raise DomainError("SOURCE_DECODE_FAILED",
                          "The file is not valid UTF-8; choose another encoding and retry") from None


def line_count(data: bytes) -> int:
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def read_all(handle) -> bytes:
    # Module-level seam so tests can interpose a mid-read change on disk.
    return handle.read()


def read_selected_file(path: Path, grant: dict) -> dict:
    root = grant.get("canonical_root")
    resolved = normalize_absolute_path(str(path))
    if root is not None:
        ensure_within_root(Path(root), resolved)
        relative = relative_parts_under(Path(root), resolved)
        ensure_no_reparse_components(Path(root), relative)
    else:
        allowed = grant.get("files") or {}
        keys = {key.casefold() for key in allowed}
        if str(resolved).casefold() not in keys:
            raise DomainError("SOURCE_OUT_OF_SCOPE",
                              "The file was not part of the approved selection")
        ensure_no_reparse_components(resolved.parent, PureWindowsPath(resolved.name))
    try:
        before = os.lstat(resolved)
    except OSError:
        raise DomainError("SOURCE_CHANGED", "The selected file is no longer available") from None
    if getattr(before, "st_file_attributes", 0) & _REPARSE_FLAG:
        raise DomainError("SOURCE_OUT_OF_SCOPE", "Links and reparse points are not supported")
    if not stat_module.S_ISREG(before.st_mode):
        raise DomainError("SOURCE_CHANGED", "The selection is not a regular file")
    if before.st_size > MAX_SINGLE_FILE_BYTES:
        raise DomainError("CONTEXT_TOO_LARGE",
                          "The file exceeds the 200000-byte text limit")
    try:
        with open(resolved, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise DomainError("SOURCE_CHANGED", "The file was replaced while it was read")
            data = read_all(handle)
            while_open = os.fstat(handle.fileno())
    except DomainError:
        raise
    except OSError:
        raise DomainError("SOURCE_CHANGED", "The file could not be read") from None
    if (while_open.st_size, while_open.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise DomainError("SOURCE_CHANGED", "The file changed while it was read")
    try:
        after = os.lstat(resolved)
    except OSError:
        raise DomainError("SOURCE_CHANGED", "The selected file is no longer available") from None
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != \
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise DomainError("SOURCE_CHANGED", "The file changed while it was read")
    final = normalize_absolute_path(str(Path(os.path.realpath(resolved))))
    if casefolded_parts(final) != casefolded_parts(resolved):
        raise DomainError("SOURCE_OUT_OF_SCOPE",
                          "The file no longer resolves to the approved path")
    text, encoding = _decode(data, grant.get("encoding"))
    return {"path": str(resolved), "content_text": text,
            "sha256": hashlib.sha256(data).hexdigest(),
            "encoding": encoding, "byte_size": len(data), "line_count": line_count(data),
            "mtime_ns": before.st_mtime_ns}
