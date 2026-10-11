"""Approved model identifiers and checkpoint-root containment helpers."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

# Remote repositories already declared by the maintained model downloader.
# Keeping the complete built-in set here avoids silently rejecting supported
# model variants merely because the older API helper carried a shorter table.
MODEL_REPO_MAPPING = {
    # Main unified repository components
    "acestep-v15-turbo": "ACE-Step/Ace-Step1.5",
    "acestep-5Hz-lm-1.7B": "ACE-Step/Ace-Step1.5",
    "vae": "ACE-Step/Ace-Step1.5",
    "Qwen3-Embedding-0.6B": "ACE-Step/Ace-Step1.5",
    # Separate LM repositories
    "acestep-5Hz-lm-0.6B": "ACE-Step/acestep-5Hz-lm-0.6B",
    "acestep-5Hz-lm-4B": "ACE-Step/acestep-5Hz-lm-4B",
    # Separate DiT repositories
    "acestep-v15-base": "ACE-Step/acestep-v15-base",
    "acestep-v15-sft": "ACE-Step/acestep-v15-sft",
    "acestep-v15-turbo-shift1": "ACE-Step/acestep-v15-turbo-shift1",
    "acestep-v15-turbo-shift3": "ACE-Step/acestep-v15-turbo-shift3",
    "acestep-v15-turbo-continuous": "ACE-Step/acestep-v15-turbo-continuous",
    "acestep-v15-xl-base": "ACE-Step/acestep-v15-xl-base",
    "acestep-v15-xl-sft": "ACE-Step/acestep-v15-xl-sft",
    "acestep-v15-xl-turbo": "ACE-Step/acestep-v15-xl-turbo",
}

# The maintained handler knows how to synchronize repository-owned code for
# these additional variants, but the existing downloader does not declare a
# remote repository for them. They may be selected only when already present
# beneath the checkpoint root; they never inherit a default remote repository.
BUILTIN_LOCAL_MODEL_IDS = frozenset(
    {
        "acestep-v15-base-sft-fix-inst",
        "acestep-v15-turbo-fix-inst-shift3",
        "acestep-v15-turbo-fix-inst-shift-continuous",
        "acestep-v15-turbo-fix-inst-shift-dynamic",
        "acestep-v15-turbo-rl",
    }
)

DEFAULT_REPO_ID = "ACE-Step/Ace-Step1.5"
_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ModelSelectionError(ValueError):
    """Raised when a caller-selected model identifier violates the registry policy."""


def _configured_local_model_ids() -> frozenset[str]:
    raw = os.getenv("ACESTEP_LOCAL_MODEL_IDS", "")
    values: set[str] = set()
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        if not _MODEL_ID_PATTERN.fullmatch(candidate) or candidate in {".", ".."}:
            raise ModelSelectionError(
                "ACESTEP_LOCAL_MODEL_IDS contains an invalid identifier: "
                f"{candidate!r}"
            )
        values.add(candidate)
    return frozenset(values)


def approved_model_ids() -> frozenset[str]:
    """Return remote, built-in-local and administrator-approved model IDs."""

    return (
        frozenset(MODEL_REPO_MAPPING)
        | BUILTIN_LOCAL_MODEL_IDS
        | _configured_local_model_ids()
    )


def approved_dit_model_ids() -> frozenset[str]:
    """Return API-selectable DiT model identifiers."""

    return frozenset(
        model_id
        for model_id in approved_model_ids()
        if model_id.startswith("acestep-v15-")
    )


def approved_lm_model_ids() -> frozenset[str]:
    """Return API-selectable language-model identifiers."""

    return frozenset(
        model_id
        for model_id in approved_model_ids()
        if model_id.startswith("acestep-5Hz-lm-")
    )


def normalize_model_identifier(
    value: str,
    *,
    allowed_ids: Iterable[str],
    field_name: str = "model",
) -> str:
    """Validate a caller value as one exact registry identifier.

    Filesystem paths, separators, traversal tokens, control characters and
    unknown names are rejected. Operators can extend the registry only with
    ``ACESTEP_LOCAL_MODEL_IDS``; those extra identifiers are local-only and are
    never assigned a default remote repository.
    """

    raw = str(value or "").strip()
    if not raw:
        raise ModelSelectionError(f"{field_name} identifier is required")
    if (
        os.path.isabs(raw)
        or "/" in raw
        or "\\" in raw
        or raw in {".", ".."}
        or not _MODEL_ID_PATTERN.fullmatch(raw)
    ):
        raise ModelSelectionError(
            f"{field_name} must be one registered model identifier, not a path"
        )

    allowed = frozenset(allowed_ids)
    if raw not in allowed:
        raise ModelSelectionError(
            f"Unsupported {field_name} identifier: {raw!r}"
        )
    return raw


def resolve_model_directory(
    checkpoint_dir: str,
    model_id: str,
    *,
    allowed_ids: Iterable[str] | None = None,
) -> str:
    """Resolve one approved model beneath the canonical checkpoint root.

    The post-resolution containment check rejects traversal and symlink escapes.
    It is safe to call before a directory exists and must be called again after
    download or extraction, because a newly created symlink can change the
    canonical destination.
    """

    allowed = approved_model_ids() if allowed_ids is None else frozenset(allowed_ids)
    normalized = normalize_model_identifier(
        model_id,
        allowed_ids=allowed,
        field_name="model",
    )
    root = os.path.normcase(os.path.realpath(checkpoint_dir))
    candidate = os.path.normcase(os.path.realpath(os.path.join(root, normalized)))
    try:
        contained = os.path.commonpath([root, candidate]) == root
    except ValueError:
        contained = False
    if not contained or candidate == root:
        raise ModelSelectionError(
            f"Resolved model directory escapes checkpoint root: {model_id!r}"
        )
    return candidate
