from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from acestep.training.path_safety import get_safe_root, set_safe_root
from acestep.training.dataset_builder_modules.dataset_path_safety import (
    DatasetPathError,
    atomic_write_with,
    resolve_dataset_audio_path,
    resolve_tensor_output_path,
    validate_sample_id,
)
from acestep.training.dataset_builder_modules.models import AudioSample, DatasetMetadata
from acestep.training.dataset_builder_modules.serialization import SerializationMixin


class _Builder(SerializationMixin):
    def __init__(self):
        self.samples = []
        self.metadata = DatasetMetadata()
        self._current_dir = ""
        self._dataset_audio_root = ""


class DatasetPathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.previous_root = get_safe_root()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        set_safe_root(str(self.root))

    def tearDown(self):
        set_safe_root(self.previous_root)
        self.temp.cleanup()

    def _audio(self, root: Path, name: str = "song.wav") -> Path:
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        path.write_bytes(b"RIFF-inert-fixture")
        return path

    def _manifest(self, path: Path, samples) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"metadata": {"name": "fixture"}, "samples": samples}),
            encoding="utf-8",
        )

    def test_sample_id_portable_grammar(self):
        for value in ("abc123", "abc-123", "A_B", "0"):
            self.assertEqual(value, validate_sample_id(value))
        for value in (
            "../escape",
            "a/b",
            r"a\b",
            "C:escape",
            ".",
            "..",
            " has-space",
            "has space",
            "CON",
            "LPT1",
            "é",
            "a" * 65,
        ):
            with self.subTest(value=value):
                with self.assertRaises(DatasetPathError):
                    validate_sample_id(value)

    def test_audio_path_accepts_regular_file_inside_root(self):
        audio_root = self.root / "audio"
        audio = self._audio(audio_root)
        self.assertEqual(
            os.path.realpath(audio),
            resolve_dataset_audio_path("song.wav", str(audio_root)),
        )
        self.assertEqual(
            os.path.realpath(audio),
            resolve_dataset_audio_path(str(audio), str(audio_root)),
        )

    def test_audio_path_rejects_absolute_and_relative_escape(self):
        audio_root = self.root / "audio"
        audio_root.mkdir()
        outside = self._audio(self.root / "outside")
        for value in (str(outside), "../outside/song.wav"):
            with self.subTest(value=value):
                with self.assertRaises(DatasetPathError):
                    resolve_dataset_audio_path(value, str(audio_root))

    def test_audio_path_rejects_symlink_escape(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        audio_root = self.root / "audio"
        audio_root.mkdir()
        outside = self._audio(self.root / "outside")
        link = audio_root / "linked.wav"
        try:
            os.symlink(outside, link)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaises(DatasetPathError):
            resolve_dataset_audio_path(str(link), str(audio_root))

    def test_tensor_path_rejects_traversal_and_existing_symlink(self):
        output = self.root / "tensors"
        output.mkdir()
        self.assertEqual(
            str(output / "sample_1.pt"),
            resolve_tensor_output_path(str(output), "sample_1"),
        )
        with self.assertRaises(DatasetPathError):
            resolve_tensor_output_path(str(output), "../outside")
        if hasattr(os, "symlink"):
            victim = self.root / "victim.txt"
            victim.write_text("keep", encoding="utf-8")
            link = output / "safe.pt"
            try:
                os.symlink(victim, link)
            except OSError:
                return
            with self.assertRaises(DatasetPathError):
                resolve_tensor_output_path(str(output), "safe")
            self.assertEqual("keep", victim.read_text(encoding="utf-8"))

    def test_atomic_writer_refuses_symlink_without_touching_target(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        directory = self.root / "out"
        directory.mkdir()
        victim = self.root / "victim.txt"
        victim.write_text("keep", encoding="utf-8")
        destination = directory / "sample.pt"
        try:
            os.symlink(victim, destination)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")

        with self.assertRaises(DatasetPathError):
            atomic_write_with(
                str(destination),
                lambda temporary: Path(temporary).write_text("new", encoding="utf-8"),
            )
        self.assertEqual("keep", victim.read_text(encoding="utf-8"))

    def test_atomic_writer_replaces_regular_destination(self):
        destination = self.root / "out" / "sample.pt"
        destination.parent.mkdir()
        destination.write_text("old", encoding="utf-8")
        atomic_write_with(
            str(destination),
            lambda temporary: Path(temporary).write_text("new", encoding="utf-8"),
        )
        self.assertEqual("new", destination.read_text(encoding="utf-8"))

    def test_valid_manifest_loads_and_canonicalizes(self):
        dataset_dir = self.root / "dataset"
        audio = self._audio(dataset_dir)
        manifest = dataset_dir / "dataset.json"
        self._manifest(
            manifest,
            [{"id": "sample1", "audio_path": "song.wav", "filename": "forged.mp3", "labeled": True}],
        )
        builder = _Builder()
        samples, status = builder.load_dataset(str(manifest))
        self.assertIn("Loaded 1", status)
        self.assertEqual(1, len(samples))
        self.assertEqual(os.path.realpath(audio), samples[0].audio_path)
        self.assertEqual("song.wav", samples[0].filename)
        self.assertEqual(os.path.realpath(dataset_dir), builder._dataset_audio_root)

    def test_manifest_escape_fails_without_partial_builder_mutation(self):
        dataset_dir = self.root / "dataset"
        dataset_dir.mkdir()
        outside = self._audio(self.root / "outside")
        manifest = dataset_dir / "dataset.json"
        self._manifest(
            manifest,
            [
                {"id": "safe1", "audio_path": str(outside)},
                {"id": "safe2", "audio_path": "missing.wav"},
            ],
        )
        builder = _Builder()
        sentinel = AudioSample(id="sentinel", audio_path="")
        builder.samples = [sentinel]
        builder.metadata.name = "keep"

        samples, status = builder.load_dataset(str(manifest))
        self.assertEqual([], samples)
        self.assertIn("Failed to load dataset", status)
        self.assertEqual([sentinel], builder.samples)
        self.assertEqual("keep", builder.metadata.name)

    def test_manifest_duplicate_ids_are_rejected(self):
        dataset_dir = self.root / "dataset"
        self._audio(dataset_dir, "a.wav")
        self._audio(dataset_dir, "b.wav")
        manifest = dataset_dir / "dataset.json"
        self._manifest(
            manifest,
            [
                {"id": "same", "audio_path": "a.wav"},
                {"id": "same", "audio_path": "b.wav"},
            ],
        )
        samples, status = _Builder().load_dataset(str(manifest))
        self.assertEqual([], samples)
        self.assertIn("Duplicate dataset sample id", status)

    def test_explicit_admin_root_allows_manifest_stored_elsewhere(self):
        audio_root = self.root / "approved-audio"
        audio = self._audio(audio_root)
        manifest = self.root / "manifests" / "dataset.json"
        self._manifest(manifest, [{"id": "sample1", "audio_path": str(audio)}])

        samples, status = _Builder().load_dataset(
            str(manifest),
            audio_root=str(audio_root),
        )
        self.assertIn("Loaded 1", status)
        self.assertEqual(os.path.realpath(audio), samples[0].audio_path)

    def test_manifest_cannot_self_declare_a_broader_root(self):
        dataset_dir = self.root / "dataset"
        dataset_dir.mkdir()
        outside = self._audio(self.root / "outside")
        manifest = dataset_dir / "dataset.json"
        manifest.write_text(
            json.dumps(
                {
                    "metadata": {
                        "name": "malicious",
                        "audio_root": str(self.root),
                    },
                    "samples": [{"id": "sample1", "audio_path": str(outside)}],
                }
            ),
            encoding="utf-8",
        )
        samples, status = _Builder().load_dataset(str(manifest))
        self.assertEqual([], samples)
        self.assertIn("escapes its approved root", status)

    def test_save_revalidates_id_and_audio_root(self):
        audio_root = self.root / "audio"
        audio = self._audio(audio_root)
        manifest = self.root / "manifests" / "saved.json"
        builder = _Builder()
        builder._dataset_audio_root = str(audio_root)
        builder.samples = [
            AudioSample(id="sample1", audio_path=str(audio), filename="forged.wav")
        ]
        status = builder.save_dataset(str(manifest))
        self.assertIn("Dataset saved", status)
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(os.path.realpath(audio), saved["samples"][0]["audio_path"])
        self.assertEqual("song.wav", saved["samples"][0]["filename"])

    def test_save_refuses_audio_outside_established_root(self):
        approved = self.root / "approved"
        approved.mkdir()
        outside = self._audio(self.root / "outside")
        builder = _Builder()
        builder._dataset_audio_root = str(approved)
        builder.samples = [AudioSample(id="sample1", audio_path=str(outside))]
        status = builder.save_dataset(str(self.root / "dataset.json"))
        self.assertIn("Failed to save dataset", status)
        self.assertFalse((self.root / "dataset.json").exists())


if __name__ == "__main__":
    unittest.main()
