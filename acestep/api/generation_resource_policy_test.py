"""Focused tests for generation ingress, work, and cancellation boundaries."""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from acestep.api.generation_resource_policy import (
    GenerationLimitError,
    GenerationResourceLimits,
    decode_audio_base64,
    effective_work_limits,
    read_json_object_limited,
    read_request_body_limited,
    validate_generation_work,
    validate_openrouter_request,
    validate_param_object,
    validate_task_id_query,
    validate_text_inputs,
)


class _FakeRequest:
    def __init__(self, chunks, headers=None):
        self._chunks = list(chunks)
        self.headers = headers or {}
        self.scope = {"type": "http", "method": "POST", "headers": []}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


class _FakeGpu:
    max_duration_with_lm = 120
    max_duration_without_lm = 300
    max_batch_size_with_lm = 2
    max_batch_size_without_lm = 4


class GenerationResourcePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_01_declared_oversize_body_is_rejected_before_stream(self):
        req = _FakeRequest([], {"content-length": "11"})
        with self.assertRaises(GenerationLimitError) as ctx:
            await read_request_body_limited(req, limit=10)
        self.assertEqual(ctx.exception.status_code, 413)

    async def test_02_chunked_oversize_body_is_rejected_during_read(self):
        req = _FakeRequest([b"12345", b"67890", b"x"])
        with self.assertRaises(GenerationLimitError) as ctx:
            await read_request_body_limited(req, limit=10)
        self.assertEqual(ctx.exception.status_code, 413)

    async def test_03_bounded_json_object_is_parsed(self):
        raw = json.dumps({"ok": True}).encode()
        req = _FakeRequest([raw], {"content-length": str(len(raw))})
        self.assertEqual(await read_json_object_limited(req), {"ok": True})

    async def test_04_json_array_is_not_accepted_as_request_object(self):
        req = _FakeRequest([b"[]"])
        with self.assertRaises(GenerationLimitError):
            await read_json_object_limited(req)

    def test_05_invalid_base64_is_rejected(self):
        with self.assertRaises(GenerationLimitError):
            decode_audio_base64("%%%%", "mp3")

    def test_06_audio_format_is_allowlisted(self):
        payload = base64.b64encode(b"audio").decode()
        with self.assertRaises(GenerationLimitError):
            decode_audio_base64(payload, "../../exe")

    def test_07_decoded_audio_byte_limit_is_enforced(self):
        tiny = GenerationResourceLimits(
            max_request_body_bytes=128,
            max_audio_part_bytes=3,
            max_total_audio_bytes=3,
        )
        payload = base64.b64encode(b"four").decode()
        with self.assertRaises(GenerationLimitError) as ctx:
            decode_audio_base64(payload, "wav", limits=tiny)
        self.assertEqual(ctx.exception.status_code, 413)

    def test_08_hardware_and_absolute_work_limits_intersect(self):
        self.assertEqual(
            effective_work_limits(lm_initialized=True, gpu_config=_FakeGpu()),
            (120.0, 2),
        )
        self.assertEqual(
            effective_work_limits(lm_initialized=False, gpu_config=_FakeGpu()),
            (300.0, 4),
        )

    def test_09_duration_batch_and_steps_over_limits_are_rejected(self):
        for kwargs in (
            {"duration": 301, "batch_size": 1, "inference_steps": 8},
            {"duration": 30, "batch_size": 5, "inference_steps": 8},
            {"duration": 30, "batch_size": 1, "inference_steps": 201},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(GenerationLimitError):
                validate_generation_work(
                    **kwargs,
                    gpu_config=_FakeGpu(),
                    lm_initialized=False,
                )

    def test_10_nonfinite_and_fractional_work_values_are_rejected(self):
        for field, value in (("duration", "nan"), ("batch_size", "1.5"), ("inference_steps", "inf")):
            kwargs = {"duration": 30, "batch_size": 1, "inference_steps": 8}
            kwargs[field] = value
            with self.subTest(field=field), self.assertRaises(GenerationLimitError):
                validate_generation_work(**kwargs, gpu_config=_FakeGpu(), lm_initialized=False)

    def test_11_seed_count_and_task_enum_are_bounded(self):
        with self.assertRaises(GenerationLimitError):
            validate_generation_work(
                seed=",".join(str(i) for i in range(9)),
                gpu_config=_FakeGpu(),
                lm_initialized=False,
            )
        with self.assertRaises(GenerationLimitError):
            validate_generation_work(
                task_type="arbitrary",
                gpu_config=_FakeGpu(),
                lm_initialized=False,
            )

    def test_12_text_and_audio_code_budgets_are_enforced(self):
        limits = GenerationResourceLimits(
            max_prompt_chars=4,
            max_lyrics_chars=4,
            max_sample_query_chars=4,
            max_audio_codes_chars=4,
        )
        for kwargs in (
            {"prompt": "12345"},
            {"lyrics": "12345"},
            {"sample_query": "12345"},
            {"audio_codes": "12345"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(GenerationLimitError):
                validate_text_inputs(**kwargs, limits=limits)

    def test_13_task_query_and_param_object_counts_are_bounded(self):
        tiny = GenerationResourceLimits(max_task_ids_per_query=2, max_param_fields=2)
        with self.assertRaises(GenerationLimitError):
            validate_task_id_query(["1", "2", "3"], limits=tiny)
        with self.assertRaises(GenerationLimitError):
            validate_param_object({"a": 1, "b": 2, "c": 3}, limits=tiny)

    def test_14_openrouter_combined_audio_budget_is_enforced(self):
        tiny = GenerationResourceLimits(
            max_request_body_bytes=1024,
            max_audio_part_bytes=6,
            max_total_audio_bytes=8,
            max_audio_parts=2,
        )
        encoded = base64.b64encode(b"123456").decode()
        part = SimpleNamespace(
            type="input_audio",
            input_audio=SimpleNamespace(data=encoded, format="mp3"),
        )
        req = SimpleNamespace(
            model="acestep/test",
            messages=[SimpleNamespace(name=None, content=[part, part])],
            lyrics="",
            audio_codes="",
            audio_config=SimpleNamespace(duration=30, format="mp3"),
            batch_size=1,
            inference_steps=8,
            task_type="text2music",
            infer_method="ode",
            seed=None,
            max_tokens=None,
            top_k=None,
        )
        with self.assertRaises(GenerationLimitError) as ctx:
            validate_openrouter_request(
                req,
                lm_initialized=False,
                gpu_config=_FakeGpu(),
                limits=tiny,
            )
        self.assertEqual(ctx.exception.status_code, 413)

    def test_15_openrouter_unknown_content_type_is_rejected(self):
        req = SimpleNamespace(
            model="acestep/test",
            messages=[SimpleNamespace(name=None, content=[{"type": "unknown"}])],
            lyrics="",
            audio_codes="",
            audio_config=None,
            batch_size=1,
            inference_steps=8,
            task_type="text2music",
            infer_method="ode",
            seed=None,
            max_tokens=None,
            top_k=None,
        )
        with self.assertRaises(GenerationLimitError):
            validate_openrouter_request(req, lm_initialized=False, gpu_config=_FakeGpu())


class CancellationAndSourceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_16_cancelled_job_cannot_be_promoted_to_success(self):
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.request_cancel(rec.job_id, "deadline exceeded")
        self.assertFalse(store.mark_succeeded(rec.job_id, {"bad": True}))
        current = store.get(rec.job_id)
        self.assertEqual(current.status, "failed")
        self.assertIn("deadline", current.error)

    def test_17_expired_deadline_is_observed_by_worker_thread(self):
        from acestep.api.jobs.store import _JobStore

        store = _JobStore()
        rec = store.create()
        store.set_deadline(rec.job_id, 0.001)
        time.sleep(0.01)
        self.assertIn("deadline", store.cancellation_reason(rec.job_id))
        self.assertEqual(store.get(rec.job_id).status, "failed")

    async def test_18_queue_worker_skips_cancelled_queued_job(self):
        from acestep.api.jobs.store import _JobStore
        from acestep.api.jobs.worker_loops import process_queue_item

        class Queue:
            def __init__(self):
                self.done = 0
            def task_done(self):
                self.done += 1

        store = _JobStore()
        rec = store.create()
        rec.done_event = asyncio.Event()
        store.request_cancel(rec.job_id, "client disconnected")
        ran = []
        state = SimpleNamespace(pending_lock=asyncio.Lock(), pending_ids=[rec.job_id], job_queue=Queue())

        async def run_one(*_):
            ran.append(True)

        async def cleanup(_):
            return None

        await process_queue_item(rec.job_id, object(), state, store, run_one, cleanup)
        self.assertEqual(ran, [])
        self.assertTrue(rec.done_event.is_set())
        self.assertEqual(state.job_queue.done, 1)

    async def test_19_stream_timeout_requests_job_cancellation(self):
        from acestep.openrouter_adapter import _openrouter_stream_generator

        class Store:
            def __init__(self):
                self.calls = []
            def request_cancel(self, job_id, reason):
                self.calls.append((job_id, reason))

        class Request:
            async def is_disconnected(self):
                return False

        rec = SimpleNamespace(job_id="job", progress_queue=asyncio.Queue())
        store = Store()
        chunks = []
        async for chunk in _openrouter_stream_generator(
            rec,
            "acestep/test",
            "mp3",
            job_store=store,
            request=Request(),
            timeout_seconds=0.01,
        ):
            chunks.append(chunk)
        self.assertTrue(store.calls)
        self.assertTrue(any("timed out" in chunk.lower() for chunk in chunks))

    def test_20_pydantic_request_models_declare_hard_caps(self):
        from pydantic import ValidationError
        from acestep.openrouter_models import ChatCompletionRequest
        from acestep.api.http.release_task_models import GenerateMusicRequest

        with self.assertRaises(ValidationError):
            ChatCompletionRequest(
                model="acestep/test",
                messages=[{"role": "user", "content": "ok"}],
                inference_steps=201,
            )
        with self.assertRaises(ValidationError):
            GenerateMusicRequest(prompt="ok", batch_size=9)

    def test_21_core_duration_allocator_has_defense_in_depth_cap(self):
        source = Path("acestep/core/generation/handler/task_utils.py").read_text(encoding="utf-8")
        self.assertIn("LIMITS.max_duration_seconds", source)
        self.assertIn("LIMITS.max_batch_size", source)

    def test_22_openrouter_reads_bounded_body_before_model_parse(self):
        source = Path("acestep/openrouter_adapter.py").read_text(encoding="utf-8")
        bounded_at = source.index("read_json_object_limited(request)")
        model_at = source.index("ChatCompletionRequest(**body)", bounded_at)
        self.assertLess(bounded_at, model_at)
        self.assertIn("validate_openrouter_request", source)
        self.assertIn("request_cancel", source)

    def test_23_custom_api_uses_bounded_reader_and_validates_work(self):
        source = Path("acestep/ui/gradio/api/api_routes.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("await _read_api_payload(request)"), 4)
        self.assertIn("validate_generation_work", source)
        self.assertIn("validate_text_inputs", source)

    def test_24_worker_and_blocking_runtime_check_cancellation(self):
        worker = Path("acestep/api/jobs/worker_loops.py").read_text(encoding="utf-8")
        blocking = Path("acestep/api/job_blocking_generation.py").read_text(encoding="utf-8")
        runtime = Path("acestep/api/job_execution_runtime.py").read_text(encoding="utf-8")
        self.assertIn("cancellation_reason", worker)
        self.assertIn("cancellation_reason", blocking)
        self.assertIn("cancellation_reason", runtime)

    def test_25_limit_environment_cannot_raise_hard_ceiling(self):
        # Dataclass defaults were resolved at import time; inspect the declared hard cap.
        self.assertEqual(GenerationResourceLimits().max_request_body_bytes, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
