import { useCallback, useEffect, useState } from 'react';

interface Workspace {
  workspace_id: string;
  name: string;
  role_tags: string[];
  revision: number;
  archived_at: string | null;
}

interface LinkRow {
  link_id: string;
  workspace_id: string;
  canonical_root: string;
  linked_at: string;
  removed_at: string | null;
}

interface DirectoryEntry {
  relative_path: string;
  size_bytes: number;
  modified_at: string;
}

interface MaterialVersion {
  version_no: number;
  byte_size: number;
  encoding: string;
  read_at: string;
}

interface MaterialSummary {
  material_id: string;
  kind: 'file' | 'text';
  display_name: string;
  current_version: MaterialVersion;
  source_path: string | null;
}

interface FreshnessItem {
  material_id: string;
  status: 'current' | 'changed' | 'missing' | 'snapshot_only';
  link_removed: boolean;
}

const FRESHNESS_LABEL: Record<FreshnessItem['status'], string> = {
  current: '与原文件一致',
  changed: '原文件已变化，可重新选择导入形成新版本',
  missing: '原文件不可用，仅剩快照',
  snapshot_only: '无有效关联，仅剩快照',
};

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

export function WorkspacePage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [links, setLinks] = useState<LinkRow[]>([]);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [materials, setMaterials] = useState<MaterialSummary[]>([]);
  const [freshness, setFreshness] = useState<Record<string, FreshnessItem['status']>>({});
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [pasteName, setPasteName] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [busy, setBusy] = useState(false);

  const call = useCallback(
    async <T,>(
      method: Parameters<typeof window.workbench.call>[0],
      params?: Record<string, unknown>,
    ): Promise<T> =>
      (await window.workbench.call(method, params)) as T,
    [],
  );

  const activeLink = links.find((link) => link.removed_at === null) ?? null;

  const loadWorkspaces = useCallback(async () => {
    const result = await call<{ items: Workspace[] }>('workspaces.list');
    setWorkspaces(result.items);
    setActiveId((current) =>
      current && result.items.some((item) => item.workspace_id === current)
        ? current
        : (result.items[0]?.workspace_id ?? null),
    );
  }, [call]);

  const loadLinks = useCallback(
    async (workspaceId: string) => {
      const result = await call<{ items: LinkRow[] }>('workspaces.listLinks', {
        workspace_id: workspaceId,
      });
      setLinks(result.items);
    },
    [call],
  );

  const loadMaterials = useCallback(
    async (workspaceId: string) => {
      const result = await call<{ items: MaterialSummary[] }>('materials.list', {
        workspace_id: workspaceId,
      });
      setMaterials(result.items);
    },
    [call],
  );

  const loadListing = useCallback(
    async (workspaceId: string, linkId: string) => {
      const result = await call<{ entries: DirectoryEntry[] }>('materials.listDirectory', {
        workspace_id: workspaceId,
        link_id: linkId,
      });
      setEntries(result.entries);
      setSelected([]);
    },
    [call],
  );

  useEffect(() => {
    loadWorkspaces().catch((cause) => setError(messageOf(cause)));
  }, [loadWorkspaces]);

  useEffect(() => {
    if (!activeId) {
      setLinks([]);
      setEntries([]);
      setMaterials([]);
      setFreshness({});
      setPreview(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [linkResult] = await Promise.all([
          call<{ items: LinkRow[] }>('workspaces.listLinks', { workspace_id: activeId }),
          loadMaterials(activeId),
        ]);
        if (cancelled) return;
        setLinks(linkResult.items);
        setEntries([]);
        setSelected([]);
        setFreshness({});
        setPreview(null);
      } catch (cause) {
        if (!cancelled) setError(messageOf(cause));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId, call, loadMaterials]);

  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }, []);

  const createWorkspace = () =>
    run(async () => {
      const name = newName.trim();
      if (!name) return;
      await call('workspaces.create', { operation_id: crypto.randomUUID(), name });
      setNewName('');
      await loadWorkspaces();
    });

  const linkDirectory = () =>
    run(async () => {
      if (!activeId) return;
      const grant = await window.workbench.chooseDirectory();
      if (!grant) return;
      await call('workspaces.linkDirectory', {
        operation_id: crypto.randomUUID(),
        workspace_id: activeId,
        grant_id: grant.grantId,
      });
      await loadLinks(activeId);
    });

  const openListing = () =>
    run(async () => {
      if (!activeId || !activeLink) return;
      await loadListing(activeId, activeLink.link_id);
    });

  const unlink = (linkId: string) =>
    run(async () => {
      if (!activeId) return;
      await call('workspaces.unlinkDirectory', {
        operation_id: crypto.randomUUID(),
        workspace_id: activeId,
        link_id: linkId,
      });
      await loadLinks(activeId);
      setEntries([]);
      setSelected([]);
      setPreview(null);
    });

  const previewFile = (entry: DirectoryEntry) =>
    run(async () => {
      if (!activeId || !activeLink) return;
      const result = await call<{ content_text: string }>('materials.previewFile', {
        workspace_id: activeId,
        link_id: activeLink.link_id,
        relative_path: entry.relative_path,
      });
      setPreview({ name: entry.relative_path, text: result.content_text });
    });

  const importSelected = () =>
    run(async () => {
      if (!activeId || !activeLink || selected.length === 0) return;
      await call('materials.importFiles', {
        operation_id: crypto.randomUUID(),
        workspace_id: activeId,
        link_id: activeLink.link_id,
        entries: selected.map((relative_path) => ({ relative_path })),
      });
      setSelected([]);
      await loadMaterials(activeId);
    });

  const importText = () =>
    run(async () => {
      if (!activeId) return;
      const name = pasteName.trim();
      if (!name || !pasteText) return;
      await call('materials.importText', {
        operation_id: crypto.randomUUID(),
        workspace_id: activeId,
        display_name: name,
        content_text: pasteText,
      });
      setPasteName('');
      setPasteText('');
      await loadMaterials(activeId);
    });

  const checkFreshness = () =>
    run(async () => {
      if (!activeId) return;
      const result = await call<{ items: FreshnessItem[] }>('materials.checkFreshness', {
        workspace_id: activeId,
      });
      const next: Record<string, FreshnessItem['status']> = {};
      for (const item of result.items) next[item.material_id] = item.status;
      setFreshness(next);
    });

  return (
    <section className="placeholder-page" aria-labelledby="page-title">
      <span className="eyebrow">SHARED SHELL · M1 TASK 04</span>
      <h1 id="page-title" tabIndex={-1}>
        资料库
      </h1>
      <p className="launcher-subtitle">关联真实目录、选择文本资料并保留只读来源快照。</p>

      {error ? (
        <p className="materials-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="materials-grid">
        <div className="materials-card" data-testid="workspace-panel">
          <h2>空间</h2>
          <div className="materials-row">
            <input
              data-testid="workspace-name"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="新空间名称"
              aria-label="新空间名称"
            />
            <button
              type="button"
              className="primary-button"
              data-testid="create-workspace"
              disabled={busy || newName.trim().length === 0}
              onClick={createWorkspace}
            >
              创建空间
            </button>
          </div>
          <ul className="materials-list" data-testid="workspace-list">
            {workspaces.map((workspace) => (
              <li key={workspace.workspace_id}>
                <button
                  type="button"
                  data-testid="workspace-item"
                  className={`materials-item ${workspace.workspace_id === activeId ? 'selected' : ''}`}
                  onClick={() => setActiveId(workspace.workspace_id)}
                >
                  <strong>{workspace.name}</strong>
                  <small>
                    {workspace.role_tags.length > 0 ? workspace.role_tags.join(' · ') : '通用'}
                  </small>
                </button>
              </li>
            ))}
            {workspaces.length === 0 ? <li className="dim">尚未创建空间。</li> : null}
          </ul>
        </div>

        <div className="materials-card" data-testid="link-panel">
          <h2>目录关联</h2>
          <button
            type="button"
            className="primary-button"
            data-testid="link-directory"
            disabled={busy || !activeId}
            onClick={linkDirectory}
          >
            选择并关联目录
          </button>
          <ul className="materials-list">
            {!activeId ? <li className="dim">先选择一个空间。</li> : null}
            {links.map((link) => (
              <li key={link.link_id} data-testid="link-item">
                <span className="mono" data-testid="link-root">
                  {link.canonical_root}
                </span>
                {link.removed_at === null ? (
                  <>
                    <button
                      type="button"
                      className="text-link"
                      data-testid="open-listing"
                      disabled={busy}
                      onClick={openListing}
                    >
                      列出文件
                    </button>
                    <button
                      type="button"
                      className="text-link"
                      data-testid="unlink-link"
                      disabled={busy}
                      onClick={() => unlink(link.link_id)}
                    >
                      移除关联
                    </button>
                  </>
                ) : (
                  <span className="pill">已移除</span>
                )}
              </li>
            ))}
          </ul>
          <p className="placeholder-note">
            关联只登记目录；读取正文始终按所选文件进行。移除关联不会删除原文件。
          </p>
        </div>

        <div className="materials-card" data-testid="listing-panel">
          <h2>目录内容（仅元数据）</h2>
          {activeLink ? (
            <>
              <ul className="materials-list" data-testid="file-list">
                {entries.map((entry) => (
                  <li key={entry.relative_path} data-testid="file-row" data-path={entry.relative_path}>
                    <label className="materials-row">
                      <input
                        type="checkbox"
                        data-testid="select-file"
                        checked={selected.includes(entry.relative_path)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, entry.relative_path]
                              : current.filter((path) => path !== entry.relative_path),
                          )
                        }
                      />
                      <span className="mono">{entry.relative_path}</span>
                      <small className="dim">{formatBytes(entry.size_bytes)}</small>
                    </label>
                    <button
                      type="button"
                      className="text-link"
                      data-testid="preview-file"
                      disabled={busy}
                      onClick={() => previewFile(entry)}
                    >
                      预览
                    </button>
                  </li>
                ))}
                {entries.length === 0 ? <li className="dim">尚未列出文件；先点击“列出文件”。</li> : null}
              </ul>
              <button
                type="button"
                className="primary-button"
                data-testid="import-selected"
                disabled={busy || selected.length === 0}
                onClick={importSelected}
              >
                导入所选（{selected.length}）
              </button>
              {preview ? (
                <pre className="materials-preview" data-testid="preview-content">
                  {`— ${preview.name} —\n${preview.text}`}
                </pre>
              ) : null}
            </>
          ) : (
            <p className="dim">没有有效的目录关联。</p>
          )}
        </div>

        <div className="materials-card" data-testid="material-panel">
          <h2>资料快照</h2>
          <div className="materials-row">
            <input
              data-testid="paste-name"
              value={pasteName}
              onChange={(event) => setPasteName(event.target.value)}
              placeholder="粘贴资料名称"
              aria-label="粘贴资料名称"
            />
            <button
              type="button"
              className="text-link"
              data-testid="check-freshness"
              disabled={busy || !activeId}
              onClick={checkFreshness}
            >
              检查原文件状态
            </button>
          </div>
          <textarea
            data-testid="paste-text"
            value={pasteText}
            onChange={(event) => setPasteText(event.target.value)}
            placeholder="粘贴文本资料（UTF-8，单份不超过 200000 字节）"
            aria-label="粘贴文本资料"
            rows={3}
          />
          <button
            type="button"
            className="primary-button"
            data-testid="import-text"
            disabled={busy || !activeId || pasteName.trim().length === 0 || pasteText.length === 0}
            onClick={importText}
          >
            保存粘贴资料
          </button>
          <ul className="materials-list" data-testid="material-list">
            {materials.map((material) => (
              <li key={material.material_id} data-testid="material-item">
                <span data-testid="material-name">{material.display_name}</span>
                <small className="dim">
                  v{material.current_version.version_no} ·{' '}
                  {formatBytes(material.current_version.byte_size)} · {material.current_version.encoding}
                </small>
                {freshness[material.material_id] ? (
                  <small data-testid="freshness-status">
                    {FRESHNESS_LABEL[freshness[material.material_id]]}
                  </small>
                ) : null}
              </li>
            ))}
            {materials.length === 0 ? <li className="dim">此空间还没有资料。</li> : null}
          </ul>
        </div>
      </div>
    </section>
  );
}
