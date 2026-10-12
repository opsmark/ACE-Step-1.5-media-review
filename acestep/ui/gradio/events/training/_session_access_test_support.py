"""Dependency-light source loader for Gradio session-access unit tests."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_REPO_ROOT = Path(__file__).resolve().parents[5]


def _package(name: str, path: Path) -> types.ModuleType:
    """Return a minimal package stub rooted at ``path``."""

    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    return module


def _load_source_module(name: str, path: Path):
    """Load one source module under a controlled import name."""

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _base_modules() -> tuple[dict[str, object], dict[str, Path]]:
    """Build package stubs and source directories for isolated imports."""

    acestep_dir = _REPO_ROOT / "acestep"
    ui_dir = acestep_dir / "ui"
    gradio_dir = ui_dir / "gradio"
    events_dir = gradio_dir / "events"
    training_events_dir = events_dir / "training"
    training_dir = acestep_dir / "training"
    modules: dict[str, object] = {
        "loguru": types.SimpleNamespace(logger=types.SimpleNamespace()),
        "acestep": _package("acestep", acestep_dir),
        "acestep.training": _package("acestep.training", training_dir),
        "acestep.ui": _package("acestep.ui", ui_dir),
        "acestep.ui.gradio": _package("acestep.ui.gradio", gradio_dir),
        "acestep.ui.gradio.events": _package("acestep.ui.gradio.events", events_dir),
        "acestep.ui.gradio.events.training": _package(
            "acestep.ui.gradio.events.training",
            training_events_dir,
        ),
    }
    paths = {
        "training": training_dir,
        "gradio": gradio_dir,
        "training_events": training_events_dir,
    }
    return modules, paths


def load_targets() -> SimpleNamespace:
    """Load real access and scan-handler modules with only lightweight stubs."""

    modules, paths = _base_modules()
    with patch.dict(sys.modules, modules):
        path_safety = _load_source_module(
            "acestep.training.path_safety",
            paths["training"] / "path_safety.py",
        )
        scope = _load_source_module(
            "acestep.ui.gradio.session_artifact_scope",
            paths["gradio"] / "session_artifact_scope.py",
        )
        access = _load_source_module(
            "acestep.ui.gradio.events.training.session_access",
            paths["training_events"] / "session_access.py",
        )

    class _UnexpectedBuilder:
        def __init__(self) -> None:
            raise AssertionError("Denied scan must not create a dataset builder")

    fake_gradio = types.SimpleNamespace(
        Progress=lambda track_tqdm=True: None,
        Warning=lambda _message: None,
        update=lambda **kwargs: {"kind": "update", **kwargs},
    )
    handler_modules, _ = _base_modules()
    handler_modules.update(
        {
            "gradio": fake_gradio,
            "acestep.training.dataset_builder": types.SimpleNamespace(
                DatasetBuilder=_UnexpectedBuilder
            ),
            "acestep.ui.gradio.events.training.session_access": access,
            "acestep.ui.gradio.events.training.training_utils": types.SimpleNamespace(
                _safe_slider=lambda maximum, **kwargs: {"maximum": maximum, **kwargs}
            ),
        }
    )
    with patch.dict(sys.modules, handler_modules):
        dataset_ops = _load_source_module(
            "acestep.ui.gradio.events.training.dataset_ops",
            paths["training_events"] / "dataset_ops.py",
        )

    return SimpleNamespace(
        access=access,
        dataset_ops=dataset_ops,
        path_safety=path_safety,
        scope=scope,
    )
