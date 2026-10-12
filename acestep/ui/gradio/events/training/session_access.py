"""Apply Gradio session ownership checks to training-dataset paths."""

from __future__ import annotations

from typing import Any

from acestep.training.path_safety import safe_path
from acestep.ui.gradio.session_artifact_scope import (
    SessionArtifactAccessError,
    authorize_session_artifact_path,
    resolve_session_artifact_scope,
)

_SCOPE_ATTR = "_gradio_session_artifact_scope"


def authorize_training_path(
    path: str,
    scope: str | None,
    *,
    must_exist: bool = True,
) -> str:
    """Apply the existing safe root and the current session ownership boundary."""

    validated = safe_path(path)
    return authorize_session_artifact_path(validated, scope, must_exist=must_exist)


def bind_builder_to_session(builder: Any, scope: str | None) -> Any:
    """Bind an in-memory dataset builder to one opaque page-session scope."""

    existing_scope = getattr(builder, _SCOPE_ATTR, None)
    active_scope = resolve_session_artifact_scope(
        scope if scope is not None else existing_scope
    )
    if existing_scope is not None and existing_scope != active_scope:
        raise SessionArtifactAccessError("Dataset builder belongs to another session")
    setattr(builder, _SCOPE_ATTR, active_scope)
    return builder


def validate_builder_audio_paths(
    builder: Any,
    *,
    must_exist: bool,
) -> tuple[bool, str]:
    """Validate every builder sample before preview, labeling, or preprocessing."""

    scope = getattr(builder, _SCOPE_ATTR, None)
    samples = list(getattr(builder, "samples", ()))
    authorized_paths: list[str] = []
    for index, sample in enumerate(samples):
        try:
            authorized_paths.append(
                authorize_training_path(
                    sample.audio_path,
                    scope,
                    must_exist=must_exist,
                )
            )
        except (SessionArtifactAccessError, ValueError) as exc:
            filename = getattr(sample, "filename", "") or f"sample {index + 1}"
            return False, f"❌ Refused audio outside this session: {filename} ({exc})"

    for sample, authorized_path in zip(samples, authorized_paths):
        sample.audio_path = authorized_path
    return True, ""


def authorize_builder_sample(builder: Any, sample_index: int) -> str:
    """Return an authorized sample audio path for preview."""

    sample = builder.samples[sample_index]
    scope = getattr(builder, _SCOPE_ATTR, None)
    return authorize_training_path(sample.audio_path, scope, must_exist=True)
