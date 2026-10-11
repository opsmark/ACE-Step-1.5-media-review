from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import torch

from acestep.training_v2.training_state_safety import (
    TrainingStateError,
    load_data_only_training_state,
)


class _ForbiddenGlobal:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def __reduce__(self):
        return (os.system, (f'touch "{self.marker}"',))


class TrainingStateSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def save(self, name: str, payload) -> Path:
        path = self.root / name
        torch.save(payload, path)
        return path

    def test_valid_optimizer_and_scheduler_state_round_trip(self) -> None:
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1)
        loss = model(torch.ones(1, 2)).sum()
        loss.backward()
        optimizer.step()
        scheduler.step()

        path = self.save(
            "valid.pt",
            {
                "epoch": torch.tensor([3]),
                "global_step": 17,
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
            },
        )
        state = load_data_only_training_state(
            str(path),
            map_location="cpu",
            base=str(self.root),
        )
        self.assertEqual((state["epoch"], state["global_step"]), (3, 17))

        replacement = torch.nn.Linear(2, 1)
        replacement_optimizer = torch.optim.Adam(replacement.parameters(), lr=0.25)
        replacement_scheduler = torch.optim.lr_scheduler.StepLR(
            replacement_optimizer,
            step_size=3,
        )
        replacement_optimizer.load_state_dict(state["optimizer_state_dict"])
        replacement_scheduler.load_state_dict(state["scheduler_state_dict"])
        self.assertEqual(replacement_optimizer.param_groups[0]["lr"], optimizer.param_groups[0]["lr"])
        self.assertEqual(replacement_scheduler.last_epoch, scheduler.last_epoch)

    def test_forbidden_pickle_global_is_rejected_without_execution(self) -> None:
        marker = self.root / "pickle-executed"
        path = self.save(
            "malicious.pt",
            {
                "epoch": 1,
                "global_step": 2,
                "payload": _ForbiddenGlobal(str(marker)),
            },
        )
        with self.assertRaises(TrainingStateError):
            load_data_only_training_state(
                str(path),
                map_location="cpu",
                base=str(self.root),
            )
        self.assertFalse(marker.exists())

    def test_loader_always_requests_weights_only(self) -> None:
        path = self.root / "fixture.pt"
        path.write_bytes(b"not-read-by-mock")
        with mock.patch(
            "acestep.training_v2.training_state_safety.torch.load",
            return_value={"epoch": 0, "global_step": 0},
        ) as load:
            load_data_only_training_state(
                str(path),
                map_location="cpu",
                base=str(self.root),
            )
        _, kwargs = load.call_args
        self.assertIs(kwargs["weights_only"], True)

    def test_no_fallback_to_unrestricted_load_after_refusal(self) -> None:
        path = self.root / "fixture.pt"
        path.write_bytes(b"rejected")
        with mock.patch(
            "acestep.training_v2.training_state_safety.torch.load",
            side_effect=RuntimeError("data-only refusal"),
        ) as load:
            with self.assertRaises(TrainingStateError):
                load_data_only_training_state(
                    str(path),
                    map_location="cpu",
                    base=str(self.root),
                )
        self.assertEqual(load.call_count, 1)
        self.assertIs(load.call_args.kwargs["weights_only"], True)

    def test_path_escape_is_rejected_before_loading(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.pt"
        outside.write_bytes(b"outside")
        try:
            with mock.patch(
                "acestep.training_v2.training_state_safety.torch.load",
            ) as load:
                with self.assertRaises(TrainingStateError):
                    load_data_only_training_state(
                        str(outside),
                        map_location="cpu",
                        base=str(self.root),
                    )
                load.assert_not_called()
        finally:
            outside.unlink(missing_ok=True)

    def test_non_mapping_state_is_rejected(self) -> None:
        path = self.save("list.pt", [1, 2, 3])
        with self.assertRaisesRegex(TrainingStateError, "must be a mapping"):
            load_data_only_training_state(str(path), base=str(self.root))

    def test_metadata_requires_nonnegative_scalar_integers(self) -> None:
        invalid = (
            {"epoch": True, "global_step": 0},
            {"epoch": -1, "global_step": 0},
            {"epoch": 1.25, "global_step": 0},
            {"epoch": torch.tensor([1, 2]), "global_step": 0},
        )
        for index, payload in enumerate(invalid):
            with self.subTest(payload=payload):
                path = self.save(f"invalid-{index}.pt", payload)
                with self.assertRaises(TrainingStateError):
                    load_data_only_training_state(str(path), base=str(self.root))

    def test_optimizer_and_scheduler_state_must_be_mappings(self) -> None:
        for field in ("optimizer_state_dict", "scheduler_state_dict"):
            path = self.save(
                f"invalid-{field}.pt",
                {"epoch": 0, "global_step": 0, field: ["unexpected"]},
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                TrainingStateError,
                field,
            ):
                load_data_only_training_state(str(path), base=str(self.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
