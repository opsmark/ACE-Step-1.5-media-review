from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from acestep.training.path_safety import get_safe_root, set_safe_root
from acestep.training.dataset_builder_modules.models import AudioSample, DatasetMetadata
from acestep.training.dataset_builder_modules.serialization import SerializationMixin


class _Builder(SerializationMixin):
    def __init__(self):
        self.samples = []
        self.metadata = DatasetMetadata()
        self._current_dir = ""
        self._dataset_audio_root = ""


class DatasetSerializationCommitTests(unittest.TestCase):
    def setUp(self):
        self.previous_root = get_safe_root()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        set_safe_root(str(self.root))

    def tearDown(self):
        set_safe_root(self.previous_root)
        self.temp.cleanup()

    def _audio(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        audio = root / "song.wav"
        audio.write_bytes(b"RIFF-inert-fixture")
        return audio

    def _builder(self, audio: Path, approved_root: Path) -> _Builder:
        builder = _Builder()
        builder._dataset_audio_root = str(approved_root)
        builder.metadata = DatasetMetadata(
            name="original-name",
            custom_tag="tag",
            tag_position="append",
            created_at="2000-01-01T00:00:00",
            num_samples=77,
            all_instrumental=False,
            genre_ratio=35,
        )
        builder.samples = [AudioSample(id="sample1", audio_path=str(audio))]
        return builder

    def test_validation_failure_preserves_all_metadata(self):
        approved = self.root / "approved"
        approved.mkdir()
        outside = self._audio(self.root / "outside")
        builder = self._builder(outside, approved)
        before = builder.metadata.to_dict()
        output = self.root / "dataset.json"

        status = builder.save_dataset(str(output), dataset_name="replacement")

        self.assertIn("Failed to save dataset", status)
        self.assertEqual(before, builder.metadata.to_dict())
        self.assertFalse(output.exists())

    def test_atomic_write_failure_preserves_all_metadata(self):
        approved = self.root / "approved"
        audio = self._audio(approved)
        builder = self._builder(audio, approved)
        before = builder.metadata.to_dict()
        output = self.root / "dataset.json"

        with mock.patch(
            "acestep.training.dataset_builder_modules.serialization.atomic_write_with",
            side_effect=OSError("synthetic durable-write failure"),
        ):
            status = builder.save_dataset(str(output), dataset_name="replacement")

        self.assertIn("Failed to save dataset", status)
        self.assertEqual(before, builder.metadata.to_dict())
        self.assertFalse(output.exists())

    def test_success_publishes_exact_staged_metadata_after_file_replace(self):
        approved = self.root / "approved"
        audio = self._audio(approved)
        builder = self._builder(audio, approved)
        output = self.root / "saved" / "dataset.json"

        status = builder.save_dataset(str(output), dataset_name="replacement")

        self.assertIn("Dataset saved", status)
        self.assertEqual("replacement", builder.metadata.name)
        self.assertEqual(1, builder.metadata.num_samples)
        self.assertNotEqual("2000-01-01T00:00:00", builder.metadata.created_at)
        self.assertEqual("tag", builder.metadata.custom_tag)
        self.assertEqual("append", builder.metadata.tag_position)
        self.assertFalse(builder.metadata.all_instrumental)
        self.assertEqual(35, builder.metadata.genre_ratio)

        saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(builder.metadata.to_dict(), saved["metadata"])
        self.assertEqual(os.path.realpath(audio), saved["samples"][0]["audio_path"])


if __name__ == "__main__":
    unittest.main()
