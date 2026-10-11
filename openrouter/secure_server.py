"""Fail-closed launcher for the standalone OpenRouter-compatible server."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from typing import Any

from acestep.network_exposure import validate_api_exposure


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACE-Step OpenRouter API server")
    parser.add_argument(
        "--host",
        default=os.getenv("OPENROUTER_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OPENROUTER_PORT", "8002")),
        help="Bind port (default: 8002)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENROUTER_API_KEY"),
        help="API key required for non-loopback binding",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    app_factory: Callable[[], Any] | None = None,
    uvicorn_run: Callable[..., Any] | None = None,
) -> None:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    api_key = str(args.api_key or "").strip() or None
    validate_api_exposure(str(args.host), api_key, service="OpenRouter API")

    if api_key is not None:
        os.environ["OPENROUTER_API_KEY"] = api_key
    else:
        os.environ.pop("OPENROUTER_API_KEY", None)

    # Import only after the validated key is published. The historical module
    # creates a global app at import time, so import ordering is security state.
    if app_factory is None:
        from openrouter.openrouter_api_server import create_app as app_factory
    if uvicorn_run is None:
        import uvicorn

        uvicorn_run = uvicorn.run

    application = app_factory()
    uvicorn_run(
        application,
        host=str(args.host),
        port=int(args.port),
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
