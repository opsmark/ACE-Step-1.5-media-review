"""Source-integration checks for Gradio session artifact isolation."""

from __future__ import annotations

import ast
import os
import re
import tempfile
import time as time_module
import types
import unittest
from typing import Any, Dict, List, Optional
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    """Return repository source text for one integration target."""

    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


class SessionIsolationSourceTests(unittest.TestCase):
    """Keep generation, training, and launch policy on the same session boundary."""

    def test_interface_shares_one_server_session_state(self) -> None:
        """Generation and training receive the same per-page opaque scope."""

        source = _source("acestep/ui/gradio/interfaces/__init__.py")
        self.assertIn(
            "session_artifact_scope = gr.State(value=SessionArtifactScopeState())",
            source,
        )
        self.assertIn(
            'generation_section["session_artifact_scope"] = session_artifact_scope',
            source,
        )
        self.assertIn(
            'training_section["session_artifact_scope"] = session_artifact_scope',
            source,
        )

    def test_foreground_and_background_generation_retain_scope(self) -> None:
        """AutoGen cannot fall back to the shared output root."""

        wiring = _source("acestep/ui/gradio/events/wiring/generation_run_wiring.py")
        wrapper = _source("acestep/ui/gradio/events/results/batch_management_wrapper.py")
        background = _source("acestep/ui/gradio/events/results/batch_management_background.py")
        progress = _source("acestep/ui/gradio/events/results/generation_progress.py")

        self.assertIn('generation_section["session_artifact_scope"]', wiring)
        self.assertIn('saved_params["session_artifact_scope"] = active_scope', wrapper)
        self.assertIn('params.get("session_artifact_scope")', background)
        self.assertIn("allocate_session_batch_directory(active_scope)", progress)
        self.assertNotIn('os.path.join(DEFAULT_RESULTS_DIR, f"batch_', progress)

    def test_auto_lrc_vtt_stays_in_session_batch_directory(self) -> None:
        """Automatic subtitles are written beside their session-owned audio."""

        source = _source("acestep/ui/gradio/events/results/lrc_utils.py")
        tree = ast.parse(source)
        wanted = {
            "parse_lrc_to_subtitles",
            "_format_vtt_timestamp",
            "lrc_to_vtt_file",
        }
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        namespace = {
            "Any": Any,
            "Dict": Dict,
            "List": List,
            "Optional": Optional,
            "logger": types.SimpleNamespace(error=lambda _message: None),
            "os": os,
            "re": re,
            "tempfile": tempfile,
            "time_module": time_module,
        }
        exec(
            compile(ast.Module(body=functions, type_ignores=[]), "<vtt>", "exec"),
            namespace,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            batch = Path(tmpdir) / "session" / "batch"
            path = namespace["lrc_to_vtt_file"](
                "[00:00.00]hello",
                total_duration=2.0,
                output_dir=str(batch),
            )
            self.assertIsNotNone(path)
            self.assertEqual(batch.resolve(), Path(path).resolve().parent)
            self.assertTrue(Path(path).read_text(encoding="utf-8").startswith("WEBVTT"))

    def test_training_scan_and_dataset_load_receive_scope(self) -> None:
        """All browser paths that can introduce media carry session state."""

        builder_wiring = _source(
            "acestep/ui/gradio/events/wiring/training_dataset_builder_wiring.py"
        )
        preprocess_wiring = _source(
            "acestep/ui/gradio/events/wiring/training_dataset_preprocess_wiring.py"
        )
        self.assertGreaterEqual(
            builder_wiring.count('training_section["session_artifact_scope"]'),
            2,
        )
        self.assertGreaterEqual(
            preprocess_wiring.count('training_section["session_artifact_scope"]'),
            2,
        )

    def test_explicit_allowed_paths_cannot_overlap_outputs(self) -> None:
        """Administrator path overrides cannot silently reopen all sessions."""

        source = _source("acestep/acestep_v15_pipeline.py")
        tree = ast.parse(source)
        function_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_paths_overlap"
        )
        namespace = {"os": os}
        exec(
            compile(ast.Module(body=[function_node], type_ignores=[]), "<paths>", "exec"),
            namespace,
        )
        overlaps = namespace["_paths_overlap"]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / "gradio_outputs"
            sibling = root / "datasets"
            self.assertTrue(overlaps(str(root), str(output)))
            self.assertTrue(overlaps(str(output / "sessions"), str(output)))
            self.assertFalse(overlaps(str(sibling), str(output)))

    def test_launch_does_not_publish_complete_output_tree(self) -> None:
        """The global generated-output directory is not an implicit allowed path."""

        source = _source("acestep/acestep_v15_pipeline.py")
        tree = ast.parse(source)
        forbidden = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets_allowed_paths = any(
                isinstance(target, ast.Name) and target.id == "allowed_paths"
                for target in node.targets
            )
            if not targets_allowed_paths:
                continue
            if isinstance(node.value, ast.List):
                forbidden.extend(
                    element.id
                    for element in node.value.elts
                    if isinstance(element, ast.Name) and element.id == "output_dir"
                )
        self.assertEqual([], forbidden)
        self.assertNotIn("allowed_paths = [output_dir]", source)
        self.assertIn("_paths_overlap(explicit_path, output_dir)", source)
        self.assertIn("must not overlap generated Gradio outputs", source)


if __name__ == "__main__":
    unittest.main()
