"""Queue worker loop helpers for API job processing."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def process_queue_item(
    job_id: str,
    req: Any,
    app_state: Any,
    store: Any,
    run_one_job: Callable[[str, Any], Awaitable[None]],
    cleanup_job_temp_files: Callable[[str], Awaitable[None]],
) -> None:
    """Process one queued item, skipping jobs cancelled before GPU admission."""
    rec = store.get(job_id)
    try:
        async with app_state.pending_lock:
            try:
                app_state.pending_ids.remove(job_id)
            except ValueError:
                pass

        cancellation_checker = getattr(store, "cancellation_reason", None)
        reason = cancellation_checker(job_id) if callable(cancellation_checker) else None
        if reason is None:
            await run_one_job(job_id, req)

        if rec and rec.progress_queue:
            if rec.status == "succeeded" and rec.result:
                await rec.progress_queue.put({"type": "result", "result": rec.result})
            elif rec.status == "failed":
                await rec.progress_queue.put({
                    "type": "error",
                    "content": rec.error or reason or "Generation failed",
                })
            await rec.progress_queue.put({"type": "done"})
        if rec and rec.done_event:
            rec.done_event.set()

    except Exception as exc:
        if rec and rec.status not in ("succeeded", "failed"):
            store.mark_failed(job_id, str(exc))
        if rec and rec.progress_queue:
            await rec.progress_queue.put({"type": "error", "content": str(exc)})
            await rec.progress_queue.put({"type": "done"})
        if rec and rec.done_event:
            rec.done_event.set()
    finally:
        await cleanup_job_temp_files(job_id)
        app_state.job_queue.task_done()


async def run_job_store_cleanup_loop(
    store: Any,
    cleanup_interval_seconds: int,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    log_fn: Callable[[str], None] = print,
) -> None:
    """Periodically cleanup completed jobs until cancelled."""

    while True:
        try:
            await sleep_fn(cleanup_interval_seconds)
            removed = store.cleanup_old_jobs()
            if removed > 0:
                stats = store.get_stats()
                log_fn(f"[API Server] Cleaned up {removed} old jobs. Current stats: {stats}")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log_fn(f"[API Server] Job cleanup error: {exc}")
