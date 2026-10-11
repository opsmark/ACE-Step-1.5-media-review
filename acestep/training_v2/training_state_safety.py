"""Data-only loading and validation for resumable training state."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any, Optional

import torch

from acestep.training.path_safety import safe_path


class TrainingStateError(ValueError):
    """A checkpoint state is unsafe, unreadable, or structurally invalid."""


def _coerce_nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise TrainingStateError(f"{field} must be a non-negative integer")
    if isinstance(value, torch.Tensor):
        if value.numel() != 1:
            raise TrainingStateError(f"{field} tensor must contain exactly one value")
        value = value.detach().cpu().item()
    if isinstance(value, float) and not value.is_integer():
        raise TrainingStateError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TrainingStateError(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise TrainingStateError(f"{field} must be a non-negative integer")
    return parsed


def load_data_only_training_state(
    state_path: str,
    *,
    map_location: Any = None,
    base: Optional[str] = None,
) -> dict[str, Any]:
    """Load a PyTorch checkpoint using the data-only deserializer.

    No fallback to unrestricted pickle loading is permitted. The returned
    mapping has normalized ``epoch`` and ``global_step`` values and validates
    optimizer/scheduler containers before callers apply them.
    """
    try:
        validated_path = safe_path(state_path, base=base)
    except ValueError as exc:
        raise TrainingStateError(str(exc)) from exc
    if not os.path.isfile(validated_path):
        raise TrainingStateError(f"Training state file not found: {validated_path}")

    try:
        state = torch.load(
            validated_path,
            map_location=map_location,
            weights_only=True,
        )
    except Exception as exc:
        raise TrainingStateError(
            "Training state was refused because it is not a readable data-only checkpoint"
        ) from exc

    if not isinstance(state, Mapping):
        raise TrainingStateError("Training state must be a mapping")

    normalized = dict(state)
    normalized["epoch"] = _coerce_nonnegative_int(
        normalized.get("epoch", 0),
        field="epoch",
    )
    normalized["global_step"] = _coerce_nonnegative_int(
        normalized.get("global_step", 0),
        field="global_step",
    )

    for field in ("optimizer_state_dict", "scheduler_state_dict"):
        value = normalized.get(field)
        if value is not None and not isinstance(value, Mapping):
            raise TrainingStateError(f"{field} must be a mapping when present")

    return normalized
