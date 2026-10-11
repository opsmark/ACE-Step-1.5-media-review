"""Security gate for the installed and container Gradio entrypoint."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence

from acestep.network_exposure import GradioExposure, validate_gradio_exposure


def _option_value(args: list[str], option: str) -> str | None:
    for index, value in enumerate(args):
        if value == option and index + 1 < len(args):
            return args[index + 1]
        if value.startswith(option + "="):
            return value.split("=", 1)[1]
    return None


def _has_option(args: list[str], option: str) -> bool:
    return option in args or any(value.startswith(option + "=") for value in args)


def _append_option(args: list[str], option: str, value: str | None) -> None:
    if value and not _has_option(args, option):
        args.extend([option, value])


def _env_bool(environ: Mapping[str, str], name: str) -> bool:
    return str(environ.get(name, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def prepare_gradio_arguments(
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> list[str]:
    """Inject reviewed environment credentials and validate effective exposure."""

    args = list(argv)
    server_name = (
        _option_value(args, "--server-name")
        or environ.get("GRADIO_SERVER_NAME")
        or "127.0.0.1"
    )
    if not _has_option(args, "--server-name"):
        args.extend(["--server-name", server_name])

    username = _option_value(args, "--auth-username") or environ.get(
        "ACESTEP_GRADIO_USERNAME"
    )
    password = _option_value(args, "--auth-password") or environ.get(
        "ACESTEP_GRADIO_PASSWORD"
    )
    api_key = _option_value(args, "--api-key") or environ.get("ACESTEP_API_KEY")
    _append_option(args, "--auth-username", username)
    _append_option(args, "--auth-password", password)
    _append_option(args, "--api-key", api_key)

    share = "--share" in args
    enable_api = "--enable-api" in args
    trusted_proxy = _env_bool(environ, "ACESTEP_TRUST_PROXY_BOUNDARY")
    proxy_bind_address = environ.get("ACESTEP_PROXY_BIND_ADDRESS")

    validate_gradio_exposure(
        GradioExposure(
            server_name=server_name,
            share=share,
            username=username,
            password=password,
            enable_api=enable_api,
            api_key=api_key,
            trusted_proxy_boundary=trusted_proxy,
            proxy_bind_address=proxy_bind_address,
        )
    )
    return args


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    pipeline_main: Callable[[], None] | None = None,
) -> None:
    """Validate launcher exposure, then delegate to the existing pipeline."""

    supplied = list(sys.argv[1:] if argv is None else argv)
    environment = os.environ if environ is None else environ
    prepared = prepare_gradio_arguments(supplied, environment)

    # Import only after exposure validation. This prevents expensive model/UI
    # initialization when the requested network boundary is unsafe.
    if pipeline_main is None:
        from acestep.acestep_v15_pipeline import main as pipeline_main

    previous = sys.argv
    try:
        sys.argv = [previous[0], *prepared]
        pipeline_main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()
