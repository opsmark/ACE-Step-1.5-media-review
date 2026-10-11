from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import torch

from acestep.training_v2 import trainer_helpers
from acestep.training_v2.training_state_safety import TrainingStateError


class _StateReceiver:
    def __init__(self) -> None:
        self.received = []

    def load_state_dict(self, state) -> None:
        self.received.append(state)


class LoKrResumeSecurityTests(unittest.TestCase):
    def make_trainer(self):
        module = SimpleNamespace(
            lycoris_net=object(),
            device=torch.device("cpu"),
        )
        return SimpleNamespace(module=module, adapter_type="lokr")

    def make_checkpoint(self, directory: Path, *, include_state: bool = True) -> Path:
        checkpoint = directory / "checkpoint"
        checkpoint.mkdir()
        (checkpoint / "lokr_weights.safetensors").write_bytes(b"inert fixture")
        if include_state:
            (checkpoint / "training_state.pt").write_bytes(b"not read by mocked loader")
        return checkpoint

    def test_refused_state_does_not_load_adapter_or_optimizer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = self.make_checkpoint(Path(directory))
            optimizer = _StateReceiver()
            scheduler = _StateReceiver()
            with mock.patch.object(
                trainer_helpers,
                "load_data_only_training_state",
                side_effect=TrainingStateError("unsafe state"),
            ), mock.patch.object(trainer_helpers, "load_lokr_weights") as load_weights:
                generator = trainer_helpers.resume_checkpoint(
                    self.make_trainer(),
                    str(checkpoint),
                    optimizer,
                    scheduler,
                )
                update = next(generator)
                with self.assertRaises(StopIteration) as stopped:
                    next(generator)

            self.assertEqual(update.kind, "warn")
            self.assertIn("Refused LoKR training state", update.msg)
            self.assertIsNone(stopped.exception.value)
            load_weights.assert_not_called()
            self.assertEqual(optimizer.received, [])
            self.assertEqual(scheduler.received, [])

    def test_valid_state_is_checked_before_adapter_and_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = self.make_checkpoint(Path(directory))
            optimizer = _StateReceiver()
            scheduler = _StateReceiver()
            events = []

            def safe_loader(*args, **kwargs):
                events.append("state")
                return {
                    "epoch": 4,
                    "global_step": 29,
                    "optimizer_state_dict": {"optimizer": "fixture"},
                    "scheduler_state_dict": {"scheduler": "fixture"},
                }

            def load_weights(*args, **kwargs):
                events.append("weights")

            with mock.patch.object(
                trainer_helpers,
                "load_data_only_training_state",
                side_effect=safe_loader,
            ), mock.patch.object(
                trainer_helpers,
                "load_lokr_weights",
                side_effect=load_weights,
            ):
                generator = trainer_helpers.resume_checkpoint(
                    self.make_trainer(),
                    str(checkpoint),
                    optimizer,
                    scheduler,
                )
                update = next(generator)
                with self.assertRaises(StopIteration) as stopped:
                    next(generator)

            self.assertEqual(events, ["state", "weights"])
            self.assertEqual(update.kind, "info")
            self.assertEqual(stopped.exception.value, (4, 29))
            self.assertEqual(optimizer.received, [{"optimizer": "fixture"}])
            self.assertEqual(scheduler.received, [{"scheduler": "fixture"}])

    def test_adapter_only_checkpoint_keeps_existing_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = self.make_checkpoint(Path(directory), include_state=False)
            with mock.patch.object(trainer_helpers, "load_lokr_weights") as load_weights:
                generator = trainer_helpers.resume_checkpoint(
                    self.make_trainer(),
                    str(checkpoint),
                    _StateReceiver(),
                    _StateReceiver(),
                )
                update = next(generator)
                with self.assertRaises(StopIteration) as stopped:
                    next(generator)

            load_weights.assert_called_once()
            self.assertEqual(update.kind, "info")
            self.assertIn("no training state", update.msg)
            self.assertIsNone(stopped.exception.value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
