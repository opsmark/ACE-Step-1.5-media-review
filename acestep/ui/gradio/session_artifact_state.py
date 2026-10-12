"""Provide a deepcopy-safe per-session artifact capability for Gradio State."""

from __future__ import annotations

from acestep.ui.gradio.session_artifact_scope import create_session_artifact_scope


class SessionArtifactScopeState:
    """Hold one opaque token and mint a fresh token whenever Gradio deepcopies it."""

    __slots__ = ("token",)

    def __init__(self) -> None:
        """Create one opaque session token."""

        self.token = create_session_artifact_scope()

    def __deepcopy__(self, memo: dict[int, object]) -> "SessionArtifactScopeState":
        """Return a fresh capability for the next independent Gradio session."""

        _ = memo
        return type(self)()
