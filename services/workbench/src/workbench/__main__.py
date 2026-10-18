"""Local stdio service; no sockets, database, or external providers."""
import argparse
import asyncio
from concurrent.futures import CancelledError
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import uuid

from workbench.contracts import DomainError, InitializeResult, PingResult, ShutdownResult
from workbench.rpc import JsonLineDecoder, RpcRouter, encode_frame, error_response, run_sync

logger = logging.getLogger("workbench")


def configure_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "backend.log", maxBytes=5 * 1024 * 1024,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


async def serve() -> None:
    loop = asyncio.get_running_loop()
    incoming = asyncio.Queue(maxsize=16)
    outgoing = asyncio.Queue(maxsize=64)
    stop = asyncio.Event()
    reader_stopped = threading.Event()
    pending = set()
    router = RpcRouter()
    decoder = JsonLineDecoder()
    instance_id = str(uuid.uuid4())
    shutdown_requested = False
    methods = ["system.initialize", "system.ping", "system.shutdown"]

    async def initialize():
        return InitializeResult(service_instance_id=instance_id, capabilities=methods).model_dump()

    async def ping():
        return PingResult(service_instance_id=instance_id).model_dump()

    async def shutdown():
        nonlocal shutdown_requested
        shutdown_requested = True
        return ShutdownResult().model_dump()

    router.register("system.initialize", initialize)
    router.register("system.ping", ping)
    router.register("system.shutdown", shutdown)

    def reader():
        # A daemon reader avoids joining an uncancellable blocking stdin read.
        def enqueue(chunk):
            if reader_stopped.is_set():
                return False
            operation = incoming.put(chunk)
            try:
                future = asyncio.run_coroutine_threadsafe(operation, loop)
            except RuntimeError:
                operation.close()
                return False
            try:
                future.result()  # Bounded queue applies backpressure to the pipe.
            except CancelledError:
                return False
            return not reader_stopped.is_set()

        try:
            while not reader_stopped.is_set():
                chunk = os.read(sys.stdin.fileno(), 64 * 1024)
                if not enqueue(chunk) or not chunk:
                    return
        except OSError:
            enqueue(b"")

    def write(wire: bytes):
        view = memoryview(wire)
        while view:
            written = os.write(sys.stdout.fileno(), view)
            if written == 0:
                raise BrokenPipeError
            view = view[written:]

    async def writer():
        while True:
            message = await outgoing.get()
            try:
                if message is None:
                    return
                await run_sync(write, encode_frame(message))
            finally:
                outgoing.task_done()

    async def dispatch(request):
        response = await router.dispatch(request, source="bridge")
        if response is not None:
            await outgoing.put(response)
        if request.get("method") == "system.shutdown" and shutdown_requested:
            # Queue the acknowledgement before waking the read loop.
            stop.set()

    async def report(error):
        logger.warning("Rejected protocol frame: %s", error.code)
        await outgoing.put(error_response(error.error.code, error.error.message))

    def completed(task):
        pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Request processing failed")
            stop.set()

    writer_task = asyncio.create_task(writer())
    stopped = asyncio.create_task(stop.wait())
    read_task = None
    threading.Thread(target=reader, daemon=True, name="workbench-stdin").start()
    logger.info("Backend started")
    try:
        while not stop.is_set():
            read_task = asyncio.create_task(incoming.get())
            done, _ = await asyncio.wait([read_task, stopped, writer_task],
                                         return_when=asyncio.FIRST_COMPLETED)
            if writer_task in done:
                await writer_task
            if stopped in done:
                break
            chunk = read_task.result()
            if not chunk:
                try:
                    decoder.finish()
                except DomainError as error:
                    await report(error)
                if pending:
                    # EOF drains ordinary requests, with bounded cleanup for long work.
                    await asyncio.wait(pending, timeout=5)
                break
            offset = 0
            while offset < len(chunk):
                newline = chunk.find(b"\n", offset)
                end = len(chunk) if newline < 0 else newline + 1
                # Feed one frame segment at a time so malformed input cannot swallow
                # a later valid frame that arrived in the same OS read.
                try:
                    for request in decoder.feed(chunk[offset:end]):
                        if len(pending) >= 128:
                            await asyncio.wait(pending | {stopped, writer_task},
                                               return_when=asyncio.FIRST_COMPLETED)
                        if stop.is_set():
                            break
                        task = asyncio.create_task(dispatch(request))
                        pending.add(task)
                        task.add_done_callback(completed)
                except DomainError as error:
                    await report(error)
                offset = end
    finally:
        reader_stopped.set()
        stopped.cancel()
        if read_task is not None:
            read_task.cancel()
        active = list(pending)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        try:
            async with asyncio.timeout(2):
                await outgoing.join()
                await outgoing.put(None)
                await writer_task
        finally:
            writer_task.cancel()
            await asyncio.gather(writer_task, stopped, *([read_task] if read_task else []),
                                 return_exceptions=True)
            logger.info("Backend stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description="Zhixu local stdio JSON-RPC service")
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="Application data directory (logs only in this scaffold)")
    args = parser.parse_args()
    try:
        configure_logging(args.data_dir)
    except (OSError, ValueError):
        print("Unable to start backend", file=sys.stderr)
        return 1
    try:
        asyncio.run(serve())
        return 0
    except (BrokenPipeError, ConnectionResetError):
        logger.info("Parent pipe closed")
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logger.error("Backend stopped unexpectedly")
        print("Backend stopped unexpectedly", file=sys.stderr)
        return 1
    finally:
        logging.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
