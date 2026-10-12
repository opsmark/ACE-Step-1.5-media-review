"""Focused tests for pre-parser body limits and extended release-task factors."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from acestep.api.generation_resource_policy import (
    GenerationLimitError,
    RequestBodyLimitMiddleware,
    default_generation_path_limits,
    validate_generate_request,
)


class _Gpu:
    max_duration_with_lm = 120
    max_duration_without_lm = 300
    max_batch_size_with_lm = 2
    max_batch_size_without_lm = 4


async def _exercise_middleware(
    *, path="/release_task", chunks=(), headers=(), limit=10, limited_path="/release_task"
):
    called = {"app": 0, "bytes": 0}
    sent = []
    pending = list(chunks)

    async def receive():
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def app(scope, inner_receive, inner_send):
        called["app"] += 1
        while True:
            message = await inner_receive()
            called["bytes"] += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await inner_send({"type": "http.response.start", "status": 204, "headers": []})
        await inner_send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(app, path_limits={limited_path: limit})
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": list(headers),
        "http_version": "1.1",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("client", 1),
        "query_string": b"",
        "root_path": "",
    }
    await middleware(scope, receive, send)
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, body, called


def _request(**updates):
    values = dict(
        prompt="normal prompt",
        global_caption="",
        lyrics="",
        sample_query="",
        audio_code_string="",
        instruction="generate music",
        lm_negative_prompt="NO USER INPUT",
        model="acestep-v15-turbo",
        lm_model_path="acestep-5Hz-lm-0.6B",
        key_scale="C major",
        time_signature="4/4",
        vocal_language="en",
        track_name="track",
        dcw_wavelet="haar",
        timesteps=None,
        track_classes=None,
        audio_duration=30,
        batch_size=1,
        inference_steps=8,
        task_type="text2music",
        infer_method="ode",
        audio_format="mp3",
        seed=-1,
    )
    values.update(updates)
    return SimpleNamespace(**values)


class RequestBodyLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_01_declared_oversize_is_rejected_before_app(self):
        status, body, called = await _exercise_middleware(
            chunks=[b"ignored"], headers=[(b"content-length", b"11")], limit=10
        )
        self.assertEqual(status, 413)
        self.assertEqual(called["app"], 0)
        self.assertIn(b"exceeds 10 bytes", body)

    async def test_02_invalid_content_length_is_rejected(self):
        status, _, called = await _exercise_middleware(
            chunks=[b"ignored"], headers=[(b"content-length", b"nope")], limit=10
        )
        self.assertEqual(status, 400)
        self.assertEqual(called["app"], 0)

    async def test_03_negative_content_length_is_rejected(self):
        status, _, called = await _exercise_middleware(
            chunks=[b"ignored"], headers=[(b"content-length", b"-1")], limit=10
        )
        self.assertEqual(status, 400)
        self.assertEqual(called["app"], 0)

    async def test_04_chunked_oversize_is_rejected_before_route_completion(self):
        status, body, called = await _exercise_middleware(
            chunks=[b"12345", b"67890", b"x"], limit=10
        )
        self.assertEqual(status, 413)
        self.assertEqual(called["app"], 1)
        self.assertEqual(called["bytes"], 10)
        self.assertIn(b"exceeds 10 bytes", body)

    async def test_05_body_at_limit_reaches_app_unchanged(self):
        status, _, called = await _exercise_middleware(
            chunks=[b"12345", b"67890"], headers=[(b"content-length", b"10")], limit=10
        )
        self.assertEqual(status, 204)
        self.assertEqual(called, {"app": 1, "bytes": 10})

    async def test_06_non_target_path_is_not_consumed_or_rejected(self):
        status, _, called = await _exercise_middleware(
            path="/unrelated", chunks=[b"12345678901"], limit=10
        )
        self.assertEqual(status, 204)
        self.assertEqual(called, {"app": 1, "bytes": 11})

    def test_07_all_network_generation_paths_have_explicit_caps(self):
        limits = default_generation_path_limits()
        for path in (
            "/release_task",
            "/v1/chat/completions",
            "/query_result",
            "/create_random_sample",
            "/format_input",
            "/v1/create_sample",
        ):
            self.assertIn(path, limits)
            self.assertGreater(limits[path], 0)


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


class ExtendedReleaseTaskTests(unittest.TestCase):
    def test_08_normal_request_passes_hardware_intersection(self):
        self.assertEqual(
            validate_generate_request(
                _request(), lm_initialized=False, gpu_config=_Gpu()
            ),
            (300.0, 4),
        )

    def test_09_timesteps_text_is_bounded(self):
        with self.assertRaises(GenerationLimitError):
            validate_generate_request(
                _request(timesteps="1" * 16_385),
                lm_initialized=False,
                gpu_config=_Gpu(),
            )

    def test_10_track_class_count_is_bounded(self):
        with self.assertRaises(GenerationLimitError):
            validate_generate_request(
                _request(track_classes=["stem"] * 65),
                lm_initialized=False,
                gpu_config=_Gpu(),
            )

    def test_11_each_track_class_is_bounded(self):
        with self.assertRaises(GenerationLimitError):
            validate_generate_request(
                _request(track_classes=["x" * 257]),
                lm_initialized=False,
                gpu_config=_Gpu(),
            )

    def test_12_release_task_work_is_intersected_with_hardware(self):
        for changes in (
            {"audio_duration": 301},
            {"batch_size": 5},
            {"inference_steps": 201},
        ):
            with self.subTest(changes=changes), self.assertRaises(GenerationLimitError):
                validate_generate_request(
                    _request(**changes), lm_initialized=False, gpu_config=_Gpu()
                )

    def test_13_route_setup_installs_body_limit_before_registration(self):
        source = Path("acestep/api/route_setup.py").read_text(encoding="utf-8")
        self.assertIn("RequestBodyLimitMiddleware", source)
        self.assertIn("default_generation_path_limits()", source)
        self.assertLess(
            source.index("RequestBodyLimitMiddleware,"),
            source.index("openrouter_router = create_openrouter_router"),
        )

    def test_14_release_task_validates_before_store_create(self):
        source = Path("acestep/api/http/release_task_route.py").read_text(encoding="utf-8")
        validate_at = source.index("validate_generate_request(")
        create_at = source.index("record = store.create()")
        self.assertLess(validate_at, create_at)
        self.assertIn("for temp_path in temp_files", source[validate_at:create_at])

    def test_15_path_caps_are_serializable_for_receipts(self):
        encoded = json.dumps(default_generation_path_limits(), sort_keys=True)
        self.assertIn("/release_task", encoded)


if __name__ == "__main__":
    unittest.main()
