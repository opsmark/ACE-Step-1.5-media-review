from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(rel: str, old: str, new: str) -> None:
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:160]!r}")
    write(rel, text.replace(old, new, 1))


# Normalize a single trailing slash and reject conflicting duplicate lengths.
replace_once(
    "acestep/api/generation_resource_policy.py",
    '''        limit = self.path_limits.get(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = {}
        for key, value in scope.get("headers", []):
            headers[key.lower()] = value
        declared_raw = headers.get(b"content-length")
        if declared_raw is not None:
            try:
                declared = int(declared_raw)
            except (TypeError, ValueError):
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared > limit:
                await self._reject(
                    scope, receive, send, 413,
                    f"Generation request body exceeds {limit} bytes",
                )
                return
''',
    '''        request_path = str(scope.get("path", ""))
        normalized_path = request_path.rstrip("/") or "/"
        limit = self.path_limits.get(request_path)
        if limit is None:
            limit = self.path_limits.get(normalized_path)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared_values = [
            value for key, value in scope.get("headers", [])
            if key.lower() == b"content-length"
        ]
        if declared_values:
            if len(set(declared_values)) != 1:
                await self._reject(
                    scope, receive, send, 400, "Conflicting Content-Length headers"
                )
                return
            declared_raw = declared_values[0]
            try:
                declared = int(declared_raw)
            except (TypeError, ValueError):
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared > limit:
                await self._reject(
                    scope, receive, send, 413,
                    f"Generation request body exceeds {limit} bytes",
                )
                return
''',
)

# Make cancellation terminal: later exception/progress paths cannot rewrite it.
replace_once(
    "acestep/api/jobs/store.py",
    '''    def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed and persist an error message."""
        with self._lock:
            record = self._jobs[job_id]
            record.status = "failed"
            record.finished_at = time.time()
            record.result = None
            record.error = error
            record.progress = record.progress if record.progress > 0 else 0.0
            record.stage = "failed"
            record.updated_at = time.time()
''',
    '''    def mark_failed(self, job_id: str, error: str) -> bool:
        """Mark failure unless a prior cancellation/success already became terminal."""
        with self._lock:
            record = self._jobs[job_id]
            if record.cancel_requested:
                record.status = "failed"
                record.result = None
                record.error = record.cancel_reason or record.error or "Generation cancelled"
                record.stage = "failed"
                record.updated_at = time.time()
                return False
            if record.status == "succeeded":
                return False
            record.status = "failed"
            record.finished_at = time.time()
            record.result = None
            record.error = error
            record.progress = record.progress if record.progress > 0 else 0.0
            record.stage = "failed"
            record.updated_at = time.time()
            return True
''',
)
replace_once(
    "acestep/api/jobs/store.py",
    '''            if not record:
                return
            record.progress = max(0.0, min(1.0, float(progress)))
''',
    '''            if not record or record.cancel_requested or record.status in ("succeeded", "failed"):
                return
            record.progress = max(0.0, min(1.0, float(progress)))
''',
)

# Win the cancellation race before model initialization and recheck afterward.
replace_once(
    "acestep/api/job_execution_runtime.py",
    '''    await ensure_models_initialized_fn(app_state)
    if not job_store.mark_running(job_id):
        raise TimeoutError(job_store.cancellation_reason(job_id) or "Generation cancelled")
    update_progress_job_cache_fn(
''',
    '''    reason = job_store.cancellation_reason(job_id)
    if reason is not None:
        raise TimeoutError(reason)
    if not job_store.mark_running(job_id):
        raise TimeoutError(job_store.cancellation_reason(job_id) or "Generation cancelled")

    await ensure_models_initialized_fn(app_state)
    reason = job_store.cancellation_reason(job_id)
    if reason is not None:
        raise TimeoutError(reason)

    update_progress_job_cache_fn(
''',
)
replace_once(
    "acestep/api/job_execution_runtime.py",
    '''    except Exception as exc:
        error_traceback = traceback.format_exc()
        log_fn(f"[API Server] Job {job_id} FAILED: {exc}")
        log_fn(f"[API Server] Traceback:\n{error_traceback}")
        job_store.mark_failed(job_id, error_traceback)
''',
    '''    except Exception as exc:
        error_traceback = traceback.format_exc()
        log_fn(f"[API Server] Job {job_id} FAILED: {exc}")
        log_fn(f"[API Server] Traceback:\n{error_traceback}")
        cancellation_reason = job_store.cancellation_reason(job_id)
        job_store.mark_failed(job_id, cancellation_reason or error_traceback)
''',
)

middleware_tests = read("acestep/api/generation_resource_middleware_test.py")
insert_marker = "\n\nclass ExtendedReleaseTaskTests(unittest.TestCase):\n"
if middleware_tests.count(insert_marker) != 1:
    raise RuntimeError("middleware test insertion marker changed")
extra_middleware_tests = '''

class RequestFramingRedTeamTests(unittest.IsolatedAsyncioTestCase):
    async def test_conflicting_duplicate_content_lengths_are_rejected(self):
        status, body, called = await _exercise_middleware(
            chunks=[b"12345"],
            headers=[(b"content-length", b"5"), (b"content-length", b"6")],
            limit=10,
        )
        self.assertEqual(status, 400)
        self.assertEqual(called["app"], 0)
        self.assertIn(b"Conflicting Content-Length", body)

    async def test_trailing_slash_cannot_bypass_path_limit(self):
        status, _, called = await _exercise_middleware(
            path="/release_task/", chunks=[b"12345678901"], limit=10
        )
        self.assertEqual(status, 413)
        self.assertEqual(called["bytes"], 0)
'''
middleware_tests = middleware_tests.replace(insert_marker, extra_middleware_tests + insert_marker, 1)
write("acestep/api/generation_resource_middleware_test.py", middleware_tests)

policy_tests = read("acestep/api/generation_resource_policy_test.py")
main_marker = '\n\nif __name__ == "__main__":\n'
if policy_tests.count(main_marker) != 1:
    raise RuntimeError("policy test insertion marker changed")
extra_policy_tests = '''

class StickyCancellationRedTeamTests(unittest.IsolatedAsyncioTestCase):
    def test_mark_failed_cannot_replace_cancellation_reason(self):
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.request_cancel(rec.job_id, "client disconnected")
        self.assertFalse(store.mark_failed(rec.job_id, "internal traceback"))
        current = store.get(rec.job_id)
        self.assertEqual(current.error, "client disconnected")
        self.assertEqual(current.status, "failed")

    def test_progress_cannot_reopen_or_relabel_cancelled_job(self):
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.request_cancel(rec.job_id, "deadline exceeded")
        store.update_progress(rec.job_id, 0.9, "running again")
        current = store.get(rec.job_id)
        self.assertEqual(current.stage, "failed")
        self.assertEqual(current.error, "deadline exceeded")

    async def test_pre_cancelled_job_does_not_initialize_models(self):
        from types import SimpleNamespace
        from acestep.api.job_execution_runtime import run_one_job_runtime
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.request_cancel(rec.job_id, "cancel before admission")
        initialized = []

        async def ensure(_):
            initialized.append(True)

        with self.assertRaises(TimeoutError):
            await run_one_job_runtime(
                app_state=SimpleNamespace(job_store=store, executor=None),
                store=None,
                job_id=rec.job_id,
                req=SimpleNamespace(model="model"),
                ensure_models_initialized_fn=ensure,
                select_generation_handler_fn=lambda **_: (_ for _ in ()).throw(AssertionError()),
                get_model_name=lambda value: value,
                build_blocking_result_fn=lambda *_: {},
                update_progress_job_cache_fn=lambda **_: None,
                update_terminal_job_cache_fn=lambda **_: None,
                map_status=lambda value: value,
                result_key_prefix="test",
                result_expire_seconds=1,
            )
        self.assertEqual(initialized, [])

    async def test_deadline_during_initialization_skips_generation(self):
        import asyncio
        from types import SimpleNamespace
        from acestep.api.job_execution_runtime import run_one_job_runtime
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.set_deadline(rec.job_id, 0.001)
        selected = []

        async def ensure(_):
            await asyncio.sleep(0.01)

        def select(**_):
            selected.append(True)
            return object(), "model"

        with self.assertRaises(TimeoutError):
            await run_one_job_runtime(
                app_state=SimpleNamespace(job_store=store, executor=None),
                store=None,
                job_id=rec.job_id,
                req=SimpleNamespace(model="model"),
                ensure_models_initialized_fn=ensure,
                select_generation_handler_fn=select,
                get_model_name=lambda value: value,
                build_blocking_result_fn=lambda *_: {},
                update_progress_job_cache_fn=lambda **_: None,
                update_terminal_job_cache_fn=lambda **_: None,
                map_status=lambda value: value,
                result_key_prefix="test",
                result_expire_seconds=1,
            )
        self.assertEqual(selected, [])
        self.assertEqual(store.get(rec.job_id).error, "Generation deadline exceeded")
'''
policy_tests = policy_tests.replace(main_marker, extra_policy_tests + main_marker, 1)
write("acestep/api/generation_resource_policy_test.py", policy_tests)

print("generation resource red-team repairs applied")
