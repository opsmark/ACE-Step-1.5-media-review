"""Focused concurrency tests for ``/release_task`` queue admission."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from acestep.api.http import release_task_route as route_module
from acestep.api.jobs.store import _JobStore

FIXTURE_AUTH = "Bearer non-operational-fixture"


class _Fixture:
    """Small in-process application with the real route/store and a harmless parser."""

    def __init__(self, temp_files=(), *, capacity: int = 1, queue=None) -> None:
        self.parsed = asyncio.Event()
        self.temp_files = list(temp_files)
        self.request_value = {"kind": "synthetic-no-generation"}
        self.fail_parse = False

        async def fixture_parser(**kwargs):
            if kwargs["authorization"] != FIXTURE_AUTH:
                raise HTTPException(status_code=401, detail="Synthetic authorization rejected")
            if self.fail_parse:
                raise HTTPException(status_code=400, detail="Synthetic parser failure")
            self.parsed.set()
            return self.request_value, list(self.temp_files)

        route_module.parse_release_task_request = fixture_parser
        self.store = _JobStore()
        self.app = FastAPI()
        state = self.app.state
        state.job_queue = queue if queue is not None else asyncio.Queue(maxsize=capacity)
        state.job_temp_files_lock = asyncio.Lock()
        state.pending_lock = asyncio.Lock()
        state.job_temp_files = {}
        state.pending_ids = []

        route_module.register_release_task_route(
            app=self.app,
            verify_token_from_request=lambda *args: None,
            wrap_response=lambda data: {"data": data},
            store=self.store,
            request_parser_cls=object,
            request_model_cls=object,
            validate_audio_path=lambda value: value,
            save_upload_to_temp=lambda *args: None,
            upload_file_type=bytes,
            default_dit_instruction="fixture",
            lm_default_temperature=0.0,
            lm_default_cfg_scale=0.0,
            lm_default_top_p=0.0,
        )
        self.endpoint = next(route.endpoint for route in self.app.routes if route.path == "/release_task")

    async def call(self):
        return await self.endpoint(None, FIXTURE_AUTH)

    def seed_queue(self):
        record = self.store.create()
        self.app.state.job_queue.put_nowait((record.job_id, {"preexisting": True}))
        self.app.state.pending_ids.append(record.job_id)
        return record

    def state(self):
        state = self.app.state
        return {
            "store": self.store.get_stats(),
            "queue_size": state.job_queue.qsize(),
            "pending_count": len(state.pending_ids),
            "temp_record_count": len(state.job_temp_files),
        }


class ReleaseTaskAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._original_parser = route_module.parse_release_task_request

    async def asyncTearDown(self) -> None:
        route_module.parse_release_task_request = self._original_parser

    async def test_known_full_rejections_do_not_create_phantom_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture()
            prior = fixture.seed_queue()
            for index in range(3):
                owned = Path(directory) / f"owned-{index}.tmp"
                owned.write_text("synthetic upload", encoding="utf-8")
                fixture.temp_files = [str(owned)]
                with self.assertRaises(HTTPException) as raised:
                    await fixture.call()
                self.assertEqual(raised.exception.status_code, 429)
                self.assertFalse(owned.exists())

            self.assertEqual(fixture.state()["store"]["queued"], 1)
            self.assertEqual(fixture.state()["queue_size"], 1)
            self.assertIs(fixture.store.get(prior.job_id), prior)

    async def test_capacity_change_while_waiting_does_not_publish_record(self) -> None:
        fixture = _Fixture()
        lock = fixture.app.state.pending_lock
        await lock.acquire()
        task = asyncio.create_task(fixture.call())
        try:
            await asyncio.wait_for(fixture.parsed.wait(), 1)
            await asyncio.sleep(0)
            prior = fixture.seed_queue()
            lock.release()
            with self.assertRaises(HTTPException) as raised:
                await task
            self.assertEqual(raised.exception.status_code, 429)
            self.assertEqual(fixture.store.get_stats()["queued"], 1)
            self.assertEqual(fixture.app.state.pending_ids, [prior.job_id])
            self.assertIs(fixture.store.get(prior.job_id), prior)
        finally:
            if lock.locked():
                lock.release()
            if not task.done():
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

    async def test_cancellation_waiting_for_each_metadata_lock_leaves_no_state(self) -> None:
        for attribute in ("pending_lock", "job_temp_files_lock"):
            with self.subTest(lock=attribute), tempfile.TemporaryDirectory() as directory:
                owned = Path(directory) / "owned-upload.tmp"
                owned.write_text("synthetic", encoding="utf-8")
                fixture = _Fixture([str(owned)])
                lock = getattr(fixture.app.state, attribute)
                await lock.acquire()
                task = asyncio.create_task(fixture.call())
                try:
                    await asyncio.wait_for(fixture.parsed.wait(), 1)
                    await asyncio.sleep(0)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertEqual(fixture.store.get_stats()["total"], 0)
                    self.assertEqual(fixture.app.state.pending_ids, [])
                    self.assertEqual(fixture.app.state.job_temp_files, {})
                    self.assertFalse(owned.exists())
                finally:
                    if lock.locked():
                        lock.release()

    async def test_put_nowait_failure_rolls_back_only_new_record(self) -> None:
        class CapacityChangedQueue(asyncio.Queue):
            def put_nowait(self, item):
                raise asyncio.QueueFull

        fixture = _Fixture(queue=CapacityChangedQueue(maxsize=1))
        prior = fixture.store.create_with_id("pre-existing-unrelated-record")
        with self.assertRaises(HTTPException) as raised:
            await fixture.call()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(fixture.store.get_stats()["total"], 1)
        self.assertIs(fixture.store.get(prior.job_id), prior)
        self.assertEqual(fixture.app.state.pending_ids, [])

    async def test_simultaneous_three_producers_admit_only_one(self) -> None:
        fixture = _Fixture()

        async def run_one():
            try:
                return await fixture.call()
            except HTTPException as error:
                return error.status_code

        results = await asyncio.gather(run_one(), run_one(), run_one())
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count(429), 2)
        self.assertEqual(fixture.store.get_stats()["queued"], 1)
        self.assertEqual(fixture.app.state.job_queue.qsize(), 1)

    async def test_normal_request_retains_metadata_and_owned_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / "owned-upload.tmp"
            owned.write_text("fixture", encoding="utf-8")
            fixture = _Fixture([str(owned)])
            response = await fixture.call()
            job_id, request = fixture.app.state.job_queue.get_nowait()
            self.assertEqual(
                response["data"],
                {"task_id": job_id, "status": "queued", "queue_position": 1},
            )
            self.assertIs(request, fixture.request_value)
            self.assertEqual(fixture.app.state.pending_ids, [job_id])
            self.assertEqual(fixture.app.state.job_temp_files[job_id], [str(owned)])
            self.assertTrue(owned.exists())

    async def test_subsequent_request_succeeds_after_capacity_is_freed(self) -> None:
        fixture = _Fixture()
        prior = fixture.seed_queue()
        with self.assertRaises(HTTPException):
            await fixture.call()

        old_id, _ = fixture.app.state.job_queue.get_nowait()
        fixture.app.state.job_queue.task_done()
        fixture.app.state.pending_ids.remove(old_id)
        fixture.store.mark_succeeded(old_id, {"fixture": True})

        response = await fixture.call()
        new_id = response["data"]["task_id"]
        self.assertNotEqual(new_id, prior.job_id)
        self.assertEqual(fixture.store.get(new_id).status, "queued")
        self.assertEqual(fixture.store.get(prior.job_id).status, "succeeded")

    async def test_discard_unsubmitted_requires_identity_and_queued_state(self) -> None:
        fixture = _Fixture()
        original = fixture.store.create_with_id("fixture-same-id")
        replacement = fixture.store.create_with_id("fixture-same-id")
        self.assertFalse(fixture.store.discard_unsubmitted(original))
        self.assertIs(fixture.store.get(original.job_id), replacement)

        fixture.store.mark_running(replacement.job_id)
        self.assertFalse(fixture.store.discard_unsubmitted(replacement))
        new_record = fixture.store.create()
        self.assertTrue(fixture.store.discard_unsubmitted(new_record))
        self.assertFalse(fixture.store.discard_unsubmitted(new_record))

    async def test_parser_failure_occurs_before_admission(self) -> None:
        fixture = _Fixture()
        fixture.fail_parse = True
        with self.assertRaises(HTTPException) as raised:
            await fixture.call()
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(fixture.store.get_stats()["total"], 0)
        self.assertEqual(fixture.app.state.pending_ids, [])

    async def test_inprocess_http_status_and_schema_are_preserved(self) -> None:
        fixture = _Fixture()
        async with AsyncClient(
            transport=ASGITransport(app=fixture.app),
            base_url="http://fixture.invalid",
        ) as client:
            unauthorized = await client.post("/release_task", json={"fixture": True})
            accepted = await client.post(
                "/release_task",
                json={"fixture": True},
                headers={"Authorization": FIXTURE_AUTH},
            )
            full = await client.post(
                "/release_task",
                json={"fixture": True},
                headers={"Authorization": FIXTURE_AUTH},
            )

        self.assertEqual(
            [unauthorized.status_code, accepted.status_code, full.status_code],
            [401, 200, 429],
        )
        self.assertEqual(accepted.json()["data"]["status"], "queued")
        self.assertEqual(full.json(), {"detail": "Server busy: queue is full"})
        self.assertEqual(fixture.store.get_stats()["total"], 1)

    async def test_queue_shutdown_rolls_back_when_runtime_supports_it(self) -> None:
        queue = asyncio.Queue(maxsize=1)
        if not hasattr(queue, "shutdown"):
            self.skipTest("asyncio.Queue.shutdown is unavailable on this Python")
        queue.shutdown()
        fixture = _Fixture(queue=queue)
        with self.assertRaises(asyncio.QueueShutDown):
            await fixture.call()
        self.assertEqual(fixture.store.get_stats()["total"], 0)
        self.assertEqual(fixture.app.state.pending_ids, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
