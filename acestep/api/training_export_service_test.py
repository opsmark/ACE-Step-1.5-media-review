from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from acestep.api.training_export_service import (
    TrainingExportConflict,
    TrainingExportError,
    TrainingExportNotFound,
    export_training_adapter,
)


class TrainingExportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_root = self.root / "training-runs"
        self.export_root = self.root / "exports"
        self.source_root.mkdir()
        self.export_root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_final(self, name: str = "run-1") -> Path:
        final = self.source_root / name / "final"
        final.mkdir(parents=True)
        (final / "adapter.safetensors").write_bytes(b"inert adapter fixture")
        return final

    def call(self, lora: str = "run-1", export: str = "release-1"):
        return export_training_adapter(
            lora_output_dir=lora,
            export_path=export,
            source_root=str(self.source_root),
            export_root=str(self.export_root),
        )

    def test_success_copies_to_new_directory(self) -> None:
        source = self.make_final()
        result = self.call()
        self.assertEqual(Path(result.source_path), source.resolve())
        self.assertEqual(Path(result.export_path), (self.export_root / "release-1").resolve())
        self.assertEqual((Path(result.export_path) / "adapter.safetensors").read_bytes(), b"inert adapter fixture")

    def test_existing_destination_is_never_deleted_or_merged(self) -> None:
        self.make_final()
        destination = self.export_root / "release-1"
        destination.mkdir()
        sentinel = destination / "unrelated.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with self.assertRaises(TrainingExportConflict):
            self.call()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_absolute_and_relative_destination_escape_are_rejected(self) -> None:
        self.make_final()
        outside = self.root / "outside"
        for requested in (str(outside), "../outside"):
            with self.subTest(requested=requested), self.assertRaises(TrainingExportError):
                self.call(export=requested)
        self.assertFalse(outside.exists())

    def test_export_root_itself_is_rejected(self) -> None:
        self.make_final()
        with self.assertRaises(TrainingExportConflict):
            self.call(export=str(self.export_root))

    def test_source_outside_configured_root_is_rejected(self) -> None:
        self.make_final()
        outside = self.root / "outside-run" / "final"
        outside.mkdir(parents=True)
        with self.assertRaises(TrainingExportError):
            self.call(lora=str(outside.parent))

    def test_source_symlink_is_rejected(self) -> None:
        target = self.root / "outside-final"
        target.mkdir()
        (target / "secret.txt").write_text("not copied", encoding="utf-8")
        run = self.source_root / "run-1"
        run.mkdir()
        try:
            os.symlink(target, run / "final", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(TrainingExportError):
            self.call()
        self.assertFalse((self.export_root / "release-1").exists())

    def test_destination_parent_symlink_is_rejected(self) -> None:
        self.make_final()
        outside = self.root / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.export_root / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(TrainingExportError):
            self.call(export="linked/release")
        self.assertFalse((outside / "release").exists())

    def test_internal_source_symlink_is_rejected(self) -> None:
        source = self.make_final()
        outside = self.root / "outside.txt"
        outside.write_text("not copied", encoding="utf-8")
        try:
            os.symlink(outside, source / "link.txt")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(TrainingExportError):
            self.call()

    def test_latest_numeric_checkpoint_is_selected(self) -> None:
        checkpoints = self.source_root / "run-1" / "checkpoints"
        for name in ("epoch_2", "epoch_10", "epoch_bad"):
            path = checkpoints / name
            path.mkdir(parents=True)
            (path / "value.txt").write_text(name, encoding="utf-8")
        result = self.call()
        self.assertEqual((Path(result.export_path) / "value.txt").read_text(encoding="utf-8"), "epoch_10")

    def test_missing_adapter_reports_not_found_without_destination(self) -> None:
        (self.source_root / "run-1").mkdir()
        with self.assertRaises(TrainingExportNotFound):
            self.call()
        self.assertFalse((self.export_root / "release-1").exists())

    def test_source_destination_overlap_is_rejected_without_mutation(self) -> None:
        source = self.make_final()
        nested_export_root = source / "exports"
        with self.assertRaises(TrainingExportConflict):
            export_training_adapter(
                lora_output_dir="run-1",
                export_path="release",
                source_root=str(self.source_root),
                export_root=str(nested_export_root),
            )
        self.assertFalse(nested_export_root.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
