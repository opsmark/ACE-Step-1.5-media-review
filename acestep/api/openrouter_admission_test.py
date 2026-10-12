"""Focused tests for bounded OpenRouter preprocessing and atomic admission."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from acestep.api.http.release_task_models import GenerateMusicRequest
from acestep.api.jobs.store import _JobStore
from acestep.openrouter_adapter import _admit_openrouter_job


class _RaceFullQueue:
    """Reports available capacity, then loses the put_nowait race."""

    def full(self):
        return False

    def put_nowait(self, _item):
        raise asyncio.QueueFull


class _DeadlineFailureStore(_JobStore):
    def set_deadline(self, job_id: str, timeout_seconds: float) -> None:
        raise RuntimeError("synthetic deadline failure")


def _state(queue):
    return SimpleNamespace(
        job_queue=queue,
        pending_lock=asyncio.Lock(),
        job_temp_files_lock=asyncio.Lock(),
        pending_ids=deque(),
        job_temp_files={},
    )


def _temp_path() -> str:
    handle, path = tempfile.mkstemp(prefix="openrouter-admission-test-")
    os.close(handle)
    return path


class OpenRouterAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_01_success_publishes_queue_and_metadata_together(self):
        queue = asyncio.Queue(maxsize=1)
        state = _state(queue)
        store = _JobStore()
        path = _temp_path()

        record = await _admit_openrouter_job(
            state,
            store,
            SimpleNamespace(name="request"),
            [path],
            streaming=True,
        )

        self.assertIs(store.get(record.job_id), record)
        self.assertIsNotNone(record.progress_queue)
        self.assertIsNone(record.done_event)
        self.assertEqual(list(state.pending_ids), [record.job_id])
        self.assertEqual(state.job_temp_files[record.job_id], [path])
        queued_id, queued_request = queue.get_nowait()
        self.assertEqual(queued_id, record.job_id)
        self.assertEqual(queued_request.name, "request")
        self.assertTrue(os.path.exists(path))
        os.remove(path)

    async def test_02_nonstreaming_admission_sets_done_event(self):
        queue = asyncio.Queue(maxsize=1)
        state = _state(queue)
        store = _JobStore()

        record = await _admit_openrouter_job(
            state,
            store,
            object(),
            [],
            streaming=False,
        )

        self.assertIsNotNone(record.done_event)
        self.assertIsNone(record.progress_queue)
        queue.get_nowait()

    async def test_03_full_queue_rejects_before_record_and_cleans_file(self):
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait(("existing", object()))
        state = _state(queue)
        store = _JobStore()
        path = _temp_path()

        with self.assertRaises(HTTPException) as ctx:
            await _admit_openrouter_job(
                state,
                store,
                object(),
                [path],
                streaming=False,
            )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(store._jobs, {})
        self.assertEqual(list(state.pending_ids), [])
        self.assertEqual(state.job_temp_files, {})
        self.assertFalse(os.path.exists(path))

    async def test_04_put_nowait_race_rolls_back_every_side_effect(self):
        state = _state(_RaceFullQueue())
        store = _JobStore()
        path = _temp_path()

        with self.assertRaises(HTTPException) as ctx:
            await _admit_openrouter_job(
                state,
                store,
                object(),
                [path],
                streaming=False,
            )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(store._jobs, {})
        self.assertEqual(list(state.pending_ids), [])
        self.assertEqual(state.job_temp_files, {})
        self.assertFalse(os.path.exists(path))

    async def test_05_failure_after_record_creation_discards_record_and_file(self):
        queue = asyncio.Queue(maxsize=1)
        state = _state(queue)
        store = _DeadlineFailureStore()
        path = _temp_path()

        with self.assertRaisesRegex(RuntimeError, "synthetic deadline failure"):
            await _admit_openrouter_job(
                state,
                store,
                object(),
                [path],
                streaming=False,
            )

        self.assertEqual(store._jobs, {})
        self.assertEqual(list(state.pending_ids), [])
        self.assertEqual(state.job_temp_files, {})
        self.assertFalse(os.path.exists(path))

    def test_06_discard_unsubmitted_has_identity_and_state_guards(self):
        store = _JobStore()
        record = store.create()
        impostor = SimpleNamespace(job_id=record.job_id, status="queued")
        self.assertFalse(store.discard_unsubmitted(impostor))
        self.assertIs(store.get(record.job_id), record)
        store.mark_running(record.job_id)
        self.assertFalse(store.discard_unsubmitted(record))
        self.assertIs(store.get(record.job_id), record)


class DurationSentinelCompatibilityTests(unittest.TestCase):
    def test_07_documented_negative_one_auto_duration_is_preserved(self):
        request = GenerateMusicRequest(audio_duration=-1)
        self.assertEqual(request.audio_duration, -1)

    def test_08_zero_and_other_negative_durations_are_rejected(self):
        for value in (0, -0.001, -0.5, -2):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                GenerateMusicRequest(audio_duration=value)

    def test_09_positive_duration_ceiling_is_preserved(self):
        self.assertEqual(GenerateMusicRequest(audio_duration=600).audio_duration, 600)
        with self.assertRaises(ValidationError):
            GenerateMusicRequest(audio_duration=600.01)


class AdmissionSourceIntegrationTests(unittest.TestCase):
    def test_10_lifespan_installs_one_openrouter_prequeue_lock(self):
        source = Path("acestep/api/lifespan_runtime.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("openrouter_prequeue_lock = asyncio.Lock()"), 1)

    def test_11_prequeue_lock_precedes_audio_materialization_and_conversion(self):
        source = Path("acestep/openrouter_adapter.py").read_text(encoding="utf-8")
        route_at = source.index("async def chat_completions")
        lock_at = source.index("async with prequeue_lock", route_at)
        materialize_at = source.index("_materialize_audio_files(audio_blobs)", lock_at)
        convert_at = source.index("handler.convert_src_audio_to_codes", materialize_at)
        admit_at = source.index("_admit_openrouter_job(", convert_at)
        self.assertLess(lock_at, materialize_at)
        self.assertLess(materialize_at, convert_at)
        self.assertLess(convert_at, admit_at)

    def test_12_admission_uses_nonblocking_put_and_shared_lock_order(self):
        source = Path("acestep/openrouter_adapter.py").read_text(encoding="utf-8")
        helper_at = source.index("async def _admit_openrouter_job")
        pending_at = source.index("async with state.pending_lock", helper_at)
        temp_at = source.index("async with state.job_temp_files_lock", pending_at)
        put_at = source.index("queue_ref.put_nowait", temp_at)
        self.assertLess(pending_at, temp_at)
        self.assertLess(temp_at, put_at)


if __name__ == "__main__":
    unittest.main()
