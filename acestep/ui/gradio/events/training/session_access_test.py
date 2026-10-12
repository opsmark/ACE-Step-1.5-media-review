"""Tests for session-owned training media access."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from _session_access_test_support import load_targets


_TARGETS = load_targets()
path_safety = _TARGETS.path_safety
scope_module = _TARGETS.scope
_DATASET_OPS = _TARGETS.dataset_ops
authorize_builder_sample = _TARGETS.access.authorize_builder_sample
authorize_training_path = _TARGETS.access.authorize_training_path
bind_builder_to_session = _TARGETS.access.bind_builder_to_session
validate_builder_audio_paths = _TARGETS.access.validate_builder_audio_paths


@contextmanager
def _isolated_training_roots():
    """Create an isolated safe root and generated-output tree."""

    previous_safe_root = path_safety.get_safe_root()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        results = root / "gradio_outputs"
        sessions = results / "sessions"
        path_safety.set_safe_root(str(root))
        with patch.object(scope_module, "DEFAULT_RESULTS_DIR", str(results)), patch.object(
            scope_module,
            "SESSION_RESULTS_DIR",
            str(sessions),
        ):
            try:
                yield root
            finally:
                path_safety.set_safe_root(previous_safe_root)


def _builder(audio_path: Path, scope: str):
    """Return a minimal builder-like object bound to ``scope``."""

    sample = SimpleNamespace(audio_path=str(audio_path), filename=audio_path.name)
    builder = SimpleNamespace(samples=[sample])
    return bind_builder_to_session(builder, scope)


class TrainingSessionAccessTests(unittest.TestCase):
    """Verify scan, preview, and processing gates share one ownership rule."""

    def test_normal_dataset_audio_remains_compatible(self) -> None:
        """A trusted non-generated dataset path remains readable."""

        with _isolated_training_roots() as root:
            audio = root / "dataset" / "song.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"audio")
            scope = scope_module.create_session_artifact_scope()
            builder = _builder(audio, scope)
            authorized, error = validate_builder_audio_paths(builder, must_exist=True)
            self.assertTrue(authorized, error)
            self.assertEqual(str(audio.resolve()), authorize_builder_sample(builder, 0))

    def test_current_session_generated_audio_is_allowed(self) -> None:
        """The active page may train from media that it generated itself."""

        with _isolated_training_roots():
            scope, batch = scope_module.allocate_session_batch_directory(None)
            audio = Path(batch) / "own.wav"
            audio.write_bytes(b"audio")
            builder = _builder(audio, scope)
            authorized, error = validate_builder_audio_paths(builder, must_exist=True)
            self.assertTrue(authorized, error)
            self.assertEqual(str(audio.resolve()), authorize_builder_sample(builder, 0))

    def test_other_session_generated_audio_is_denied(self) -> None:
        """A builder cannot preview or process media owned by another page."""

        with _isolated_training_roots():
            scope_a, _batch_a = scope_module.allocate_session_batch_directory(None)
            _scope_b, batch_b = scope_module.allocate_session_batch_directory(None)
            audio_b = Path(batch_b) / "other.wav"
            audio_b.write_bytes(b"audio")
            builder = _builder(audio_b, scope_a)
            authorized, error = validate_builder_audio_paths(builder, must_exist=True)
            self.assertFalse(authorized)
            self.assertIn("outside this session", error)
            with self.assertRaises(ValueError):
                authorize_builder_sample(builder, 0)

    def test_builder_cannot_be_rebound_to_another_session(self) -> None:
        """A server-side builder keeps the page scope that first owned it."""

        with _isolated_training_roots() as root:
            audio = root / "dataset" / "song.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"audio")
            builder = _builder(audio, scope_module.create_session_artifact_scope())
            with self.assertRaises(ValueError):
                bind_builder_to_session(
                    builder,
                    scope_module.create_session_artifact_scope(),
                )

    def test_failed_validation_does_not_partially_rewrite_builder(self) -> None:
        """A later denied sample leaves earlier sample paths unchanged."""

        with _isolated_training_roots() as root:
            scope_a, _batch_a = scope_module.allocate_session_batch_directory(None)
            _scope_b, batch_b = scope_module.allocate_session_batch_directory(None)
            normal_audio = root / "dataset" / "song.wav"
            normal_audio.parent.mkdir()
            normal_audio.write_bytes(b"audio")
            other_audio = Path(batch_b) / "other.wav"
            other_audio.write_bytes(b"audio")
            noncanonical = os.path.join(
                str(normal_audio.parent), "..", "dataset", "song.wav"
            )
            builder = SimpleNamespace(
                samples=[
                    SimpleNamespace(audio_path=noncanonical, filename="song.wav"),
                    SimpleNamespace(audio_path=str(other_audio), filename="other.wav"),
                ]
            )
            bind_builder_to_session(builder, scope_a)
            authorized, _error = validate_builder_audio_paths(builder, must_exist=True)
            self.assertFalse(authorized)
            self.assertEqual(noncanonical, builder.samples[0].audio_path)

    def test_scan_handler_preserves_state_for_other_session(self) -> None:
        """The Gradio scanner refuses another page before constructing a builder."""

        with _isolated_training_roots():
            scope_a, _batch_a = scope_module.allocate_session_batch_directory(None)
            _scope_b, batch_b = scope_module.allocate_session_batch_directory(None)
            old_state = object()
            result = _DATASET_OPS.scan_directory(
                batch_b, "dataset", "", "prepend", False, old_state, scope_a
            )
            self.assertIs(old_state, result[3])
            self.assertIn("outside this session", result[1])

    def test_preview_handler_never_returns_other_session_path(self) -> None:
        """The preview handler fails closed for another page's audio."""

        with _isolated_training_roots():
            scope_a, _batch_a = scope_module.allocate_session_batch_directory(None)
            _scope_b, batch_b = scope_module.allocate_session_batch_directory(None)
            audio_b = Path(batch_b) / "other.wav"
            audio_b.write_bytes(b"audio")
            sample = SimpleNamespace(
                audio_path=str(audio_b),
                filename="other.wav",
                has_raw_lyrics=lambda: False,
            )
            builder = SimpleNamespace(samples=[sample])
            bind_builder_to_session(builder, scope_a)
            result = _DATASET_OPS.get_sample_preview(0, builder)
            self.assertIsNone(result[0])
            self.assertNotIn(str(audio_b), result)

    def test_save_handler_rejects_builder_from_another_session(self) -> None:
        """The save handler cannot re-home a dataset builder."""

        with _isolated_training_roots() as root:
            audio = root / "dataset" / "song.wav"
            audio.parent.mkdir()
            audio.write_bytes(b"audio")
            builder = _builder(audio, scope_module.create_session_artifact_scope())
            status, _update = _DATASET_OPS.save_dataset(
                str(root / "dataset.json"),
                "dataset",
                builder,
                scope_module.create_session_artifact_scope(),
            )
            self.assertIn("outside this session", status)

    def test_shared_generated_output_root_cannot_be_scanned(self) -> None:
        """The scanner cannot enumerate all opaque session directories."""

        with _isolated_training_roots():
            scope, _batch = scope_module.allocate_session_batch_directory(None)
            with self.assertRaises(ValueError):
                authorize_training_path(
                    scope_module.DEFAULT_RESULTS_DIR,
                    scope,
                    must_exist=True,
                )


if __name__ == "__main__":
    unittest.main()
