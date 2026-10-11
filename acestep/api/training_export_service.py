"""Safe, non-destructive export of trained adapter directories."""

from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass
from typing import Optional

from acestep.training.path_safety import get_safe_root, safe_path

_EPOCH_PATTERN = re.compile(r"^epoch_(\d+)$")


class TrainingExportError(ValueError):
    """Base class for a rejected training export request."""


class TrainingExportNotFound(TrainingExportError):
    """Requested training output does not contain an exportable adapter."""


class TrainingExportConflict(TrainingExportError):
    """Destination already exists or overlaps protected data."""


@dataclass(frozen=True)
class TrainingExportResult:
    source_path: str
    export_path: str


def _trusted_root(explicit: Optional[str], env_name: str, fallback: str) -> str:
    value = explicit or os.getenv(env_name) or fallback
    return os.path.normpath(os.path.realpath(value))


def _candidate_path(user_path: str, root: str) -> str:
    """Return the lexical absolute path used to inspect symlink components."""
    if os.path.isabs(user_path):
        return os.path.abspath(os.path.normpath(user_path))
    return os.path.abspath(os.path.normpath(os.path.join(root, user_path)))


def _reject_symlink_components(user_path: str, root: str, *, label: str) -> None:
    candidate = _candidate_path(user_path, root)
    try:
        relative = os.path.relpath(candidate, root)
    except ValueError as exc:
        raise TrainingExportError(f"{label} is on a different filesystem root") from exc
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise TrainingExportError(f"{label} escapes its configured root")

    current = root
    if os.path.islink(current):
        raise TrainingExportError(f"{label} root must not be a symlink")
    if relative == os.curdir:
        return
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            raise TrainingExportError(f"{label} contains a symlink component: {current}")


def _contains_path(parent: str, child: str) -> bool:
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def _reject_source_links_and_special_files(source_path: str) -> None:
    for current_root, directory_names, file_names in os.walk(source_path, followlinks=False):
        for name in [*directory_names, *file_names]:
            path = os.path.join(current_root, name)
            if os.path.islink(path):
                raise TrainingExportError(f"Training export source contains a symlink: {path}")
            mode = os.stat(path, follow_symlinks=False).st_mode
            if name in file_names and not stat.S_ISREG(mode):
                raise TrainingExportError(f"Training export source contains a non-regular file: {path}")


def _select_source(lora_output_dir: str, source_root: str) -> str:
    _reject_symlink_components(lora_output_dir, source_root, label="Training output path")
    try:
        output_dir = safe_path(lora_output_dir, base=source_root)
    except ValueError as exc:
        raise TrainingExportError(str(exc)) from exc
    if not os.path.isdir(output_dir):
        raise TrainingExportNotFound(f"Training output directory not found: {output_dir}")

    final_input = os.path.join(output_dir, "final")
    if os.path.islink(final_input):
        raise TrainingExportError("Final adapter directory must not be a symlink")
    if os.path.isdir(final_input):
        source_path = safe_path(final_input, base=output_dir)
        _reject_source_links_and_special_files(source_path)
        return source_path

    checkpoints_input = os.path.join(output_dir, "checkpoints")
    if os.path.islink(checkpoints_input):
        raise TrainingExportError("Checkpoint directory must not be a symlink")
    if not os.path.isdir(checkpoints_input):
        raise TrainingExportNotFound(f"No trained model found in {output_dir}")

    checkpoints: list[tuple[int, str]] = []
    for entry in os.listdir(checkpoints_input):
        match = _EPOCH_PATTERN.fullmatch(entry)
        if not match:
            continue
        raw_path = os.path.join(checkpoints_input, entry)
        if os.path.islink(raw_path) or not os.path.isdir(raw_path):
            continue
        checkpoints.append((int(match.group(1)), raw_path))
    if not checkpoints:
        raise TrainingExportNotFound("No checkpoints found")

    _, selected = max(checkpoints, key=lambda item: item[0])
    source_path = safe_path(selected, base=checkpoints_input)
    _reject_source_links_and_special_files(source_path)
    return source_path


def export_training_adapter(
    *,
    lora_output_dir: str,
    export_path: str,
    source_root: Optional[str] = None,
    export_root: Optional[str] = None,
) -> TrainingExportResult:
    """Copy one trained adapter into a new destination under an admin root.

    Existing destinations are never removed or overwritten. Caller-controlled
    source and destination paths are constrained independently, symlinked path
    components are rejected, and source/destination overlap is refused.
    """
    configured_source_root = _trusted_root(
        source_root,
        "ACESTEP_TRAINING_OUTPUT_ROOT",
        get_safe_root(),
    )
    configured_export_root = _trusted_root(
        export_root,
        "ACESTEP_TRAINING_EXPORT_ROOT",
        os.path.join(get_safe_root(), "training_exports"),
    )

    source_path = _select_source(lora_output_dir.strip(), configured_source_root)
    raw_export_path = export_path.strip()
    if not raw_export_path:
        raise TrainingExportError("Export destination path is required")
    _reject_symlink_components(raw_export_path, configured_export_root, label="Export path")
    try:
        destination = safe_path(raw_export_path, base=configured_export_root)
    except ValueError as exc:
        raise TrainingExportError(str(exc)) from exc

    if destination == configured_export_root:
        raise TrainingExportConflict("Export root itself cannot be used as a destination")
    if os.path.lexists(destination):
        raise TrainingExportConflict(f"Export destination already exists: {destination}")
    if _contains_path(source_path, destination) or _contains_path(destination, source_path):
        raise TrainingExportConflict("Training source and export destination must not overlap")

    os.makedirs(configured_export_root, exist_ok=True)
    parent = os.path.dirname(destination)
    _reject_symlink_components(parent, configured_export_root, label="Export parent")
    parent = safe_path(parent, base=configured_export_root)
    os.makedirs(parent, exist_ok=True)
    # copytree is intentionally non-overwriting. A concurrent creation causes a
    # failure instead of recursive deletion or merge.
    shutil.copytree(source_path, destination, symlinks=True)
    return TrainingExportResult(source_path=source_path, export_path=destination)
