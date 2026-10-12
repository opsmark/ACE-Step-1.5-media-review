"""Tests for opaque per-session Gradio artifact directories."""

from __future__ import annotations

import copy
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def _package(name: str, path: Path) -> types.ModuleType:
    """Return a minimal package stub rooted at ``path``."""

    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    return module


def _load_module(name: str, path: Path):
    """Load one source module without importing the full Gradio package."""

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_targets():
    """Load the real scope and state modules with lightweight package stubs."""

    gradio_dir = Path(__file__).resolve().parent
    ui_dir = gradio_dir.parent
    acestep_dir = ui_dir.parent
    modules = {
        "acestep": _package("acestep", acestep_dir),
        "acestep.ui": _package("acestep.ui", ui_dir),
        "acestep.ui.gradio": _package("acestep.ui.gradio", gradio_dir),
    }
    with patch.dict(sys.modules, modules):
        scope = _load_module(
            "acestep.ui.gradio.session_artifact_scope",
            gradio_dir / "session_artifact_scope.py",
        )
        state = _load_module(
            "acestep.ui.gradio.session_artifact_state",
            gradio_dir / "session_artifact_state.py",
        )
    return scope, state


scope_module, _state_module = _load_targets()
SessionArtifactAccessError = scope_module.SessionArtifactAccessError
SessionArtifactScopeState = _state_module.SessionArtifactScopeState


@contextmanager
def _isolated_roots():
    """Redirect managed artifact roots into a temporary directory."""

    with tempfile.TemporaryDirectory() as tmpdir:
        results = Path(tmpdir) / "gradio_outputs"
        sessions = results / "sessions"
        with patch.object(scope_module, "DEFAULT_RESULTS_DIR", str(results)), patch.object(
            scope_module,
            "SESSION_RESULTS_DIR",
            str(sessions),
        ):
            yield Path(tmpdir), results, sessions


class SessionArtifactScopeTests(unittest.TestCase):
    """Verify generated artifacts remain inside one opaque page session."""

    def test_gradio_deepcopy_mints_distinct_session_capabilities(self) -> None:
        """The mechanism Gradio uses for State creates one token per session."""

        initial = SessionArtifactScopeState()
        first = copy.deepcopy(initial)
        second = copy.deepcopy(initial)

        self.assertNotEqual(initial.token, first.token)
        self.assertNotEqual(first.token, second.token)
        self.assertEqual(first.token, scope_module.resolve_session_artifact_scope(first))

    def test_two_scopes_get_disjoint_roots_and_files(self) -> None:
        """One session cannot authorize another session's generated file."""

        with _isolated_roots():
            scope_a, batch_a = scope_module.allocate_session_batch_directory(None)
            scope_b, batch_b = scope_module.allocate_session_batch_directory(None)
            audio_a = Path(batch_a) / "a.wav"
            audio_b = Path(batch_b) / "b.wav"
            audio_a.write_bytes(b"a")
            audio_b.write_bytes(b"b")

            self.assertNotEqual(scope_a, scope_b)
            self.assertNotEqual(Path(batch_a).parent, Path(batch_b).parent)
            self.assertEqual(
                os.path.realpath(audio_a),
                scope_module.authorize_session_artifact_path(audio_a, scope_a),
            )
            with self.assertRaises(SessionArtifactAccessError):
                scope_module.authorize_session_artifact_path(audio_b, scope_a)

    def test_scope_prefix_collision_is_not_containment(self) -> None:
        """A sibling directory with the scope as a prefix remains inaccessible."""

        with _isolated_roots() as (_tmp, _results, sessions):
            scope, _batch = scope_module.allocate_session_batch_directory(None)
            collision = sessions / f"{scope}extra"
            collision.mkdir()
            audio = collision / "other.wav"
            audio.write_bytes(b"other")

            with self.assertRaises(SessionArtifactAccessError):
                scope_module.authorize_session_artifact_path(audio, scope)

    def test_batch_directories_are_unique_within_one_scope(self) -> None:
        """Repeated generations do not collide inside the same session."""

        with _isolated_roots():
            scope = scope_module.create_session_artifact_scope()
            _, first = scope_module.allocate_session_batch_directory(scope)
            _, second = scope_module.allocate_session_batch_directory(scope)

            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).parent, Path(second).parent)

    def test_managed_root_and_invalid_scope_are_refused(self) -> None:
        """A caller cannot select the shared output root or forge a scope."""

        with _isolated_roots() as (_tmp, results, sessions):
            scope, _batch = scope_module.allocate_session_batch_directory(None)
            with self.assertRaises(SessionArtifactAccessError):
                scope_module.authorize_session_artifact_path(results, scope)
            with self.assertRaises(SessionArtifactAccessError):
                scope_module.authorize_session_artifact_path(sessions, scope)
            with self.assertRaises(SessionArtifactAccessError):
                scope_module.session_artifact_root("../other", create=True)

    def test_symlink_escape_is_refused(self) -> None:
        """A symlink inside a session cannot redirect access outside its root."""

        with _isolated_roots() as (tmp, _results, _sessions):
            scope, batch = scope_module.allocate_session_batch_directory(None)
            outside = tmp / "outside.wav"
            outside.write_bytes(b"outside")
            link = Path(batch) / "escape.wav"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this test platform")

            with self.assertRaises(SessionArtifactAccessError):
                scope_module.authorize_session_artifact_path(link, scope)

    def test_symlinked_managed_root_is_refused(self) -> None:
        """The application cannot be redirected through a replaced sessions root."""

        with _isolated_roots() as (tmp, results, sessions):
            results.mkdir()
            external = tmp / "external_sessions"
            external.mkdir()
            try:
                sessions.symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable on this test platform")

            with self.assertRaises(SessionArtifactAccessError):
                scope_module.allocate_session_batch_directory(None)

    def test_non_managed_path_keeps_the_callers_trust_policy(self) -> None:
        """Normal trusted dataset paths are not reclassified as session output."""

        with _isolated_roots() as (tmp, _results, _sessions):
            dataset_audio = tmp / "dataset" / "song.wav"
            dataset_audio.parent.mkdir()
            dataset_audio.write_bytes(b"audio")

            resolved = scope_module.authorize_session_artifact_path(
                dataset_audio,
                None,
            )

            self.assertEqual(os.path.realpath(dataset_audio), resolved)
            self.assertFalse(scope_module.is_managed_artifact_path(dataset_audio))


if __name__ == "__main__":
    unittest.main()
