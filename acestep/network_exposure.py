"""Fail-closed exposure policy for official ACE-Step launchers."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


class ExposurePolicyError(ValueError):
    """Raised when a launcher would expose an unauthenticated service."""


def is_loopback_host(host: str) -> bool:
    """Return whether ``host`` is an IP/hostname limited to this machine."""

    normalized = str(host or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


@dataclass(frozen=True)
class GradioExposure:
    server_name: str
    share: bool
    username: str | None
    password: str | None
    enable_api: bool
    api_key: str | None
    trusted_proxy_boundary: bool = False
    proxy_bind_address: str | None = None


def validate_api_exposure(host: str, api_key: str | None, *, service: str) -> None:
    """Reject a non-loopback API bind without an explicit key."""

    if not is_loopback_host(host) and not _present(api_key):
        raise ExposurePolicyError(
            f"Refusing to expose {service} on {host!r} without an API key"
        )


def validate_gradio_exposure(config: GradioExposure) -> None:
    """Validate UI/API exposure before importing or starting Gradio.

    A container may bind internally to all interfaces while its explicitly
    declared host/proxy boundary is loopback-only. That exception is accepted
    only when the launcher supplies both the trust flag and a loopback host
    binding; merely setting the trust flag is insufficient.
    """

    username_present = _present(config.username)
    password_present = _present(config.password)
    if username_present != password_present:
        raise ExposurePolicyError(
            "Gradio authentication requires both username and password"
        )

    proxy_limited = (
        config.trusted_proxy_boundary
        and is_loopback_host(config.proxy_bind_address or "")
        and not config.share
    )
    externally_reachable = (
        config.share
        or (not is_loopback_host(config.server_name) and not proxy_limited)
    )

    if externally_reachable and not (username_present and password_present):
        raise ExposurePolicyError(
            "Refusing externally reachable Gradio UI without username/password"
        )
    if (externally_reachable or proxy_limited) and config.enable_api and not _present(
        config.api_key
    ):
        raise ExposurePolicyError(
            "Gradio API endpoints require an API key outside direct loopback"
        )
