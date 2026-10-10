"""CLI bootstrap helpers for launching the API server process."""

from __future__ import annotations

import argparse
import ipaddress
import os
from typing import Any, Callable, Optional

import uvicorn


def _is_loopback_host(host: str) -> bool:
    """Return whether a bind host is limited to the local machine."""

    normalized = host.strip().lower()
    if normalized == "localhost":
        return True

    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _resolve_app_factory(
    app_factory: Optional[Callable[[], Any]],
) -> Callable[[], Any]:
    """Return the supplied app factory or import the production factory lazily."""

    if app_factory is not None:
        return app_factory

    from acestep.api_server import create_app

    return create_app


def run_api_server_main(
    env_bool: Callable[[str, bool], bool],
    argv: Optional[list[str]] = None,
    app_factory: Optional[Callable[[], Any]] = None,
) -> None:
    """Parse CLI args, apply overrides, build the app, and start uvicorn.

    Args:
        env_bool: Boolean env parser used for defaults.
        argv: Optional explicit arg list used by tests. Defaults to process argv.
        app_factory: Optional application factory used by tests. The production
            factory is imported lazily after all environment overrides are set.

    Raises:
        SystemExit: If an unauthenticated server is configured to bind beyond
            the loopback interface.
    """

    parser = argparse.ArgumentParser(description="ACE-Step API server")
    parser.add_argument(
        "--host",
        default=os.getenv("ACESTEP_API_HOST", "127.0.0.1"),
        help="Bind host (default from ACESTEP_API_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACESTEP_API_PORT", "8001")),
        help="Bind port (default from ACESTEP_API_PORT or 8001)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("ACESTEP_API_KEY", None),
        help="API key for authentication (default from ACESTEP_API_KEY)",
    )
    parser.add_argument(
        "--download-source",
        type=str,
        choices=["huggingface", "modelscope", "auto"],
        default=os.getenv("ACESTEP_DOWNLOAD_SOURCE", "auto"),
        help="Preferred model download source: auto (default), huggingface, or modelscope",
    )
    parser.add_argument(
        "--init-llm",
        action="store_true",
        default=env_bool("ACESTEP_INIT_LLM", False),
        help="Initialize LLM even if GPU memory is insufficient (may cause OOM). "
        "Can also be set via ACESTEP_INIT_LLM=true environment variable.",
    )
    parser.add_argument(
        "--lm-model-path",
        type=str,
        default=os.getenv("ACESTEP_LM_MODEL_PATH", ""),
        help="LM model to load (e.g., 'acestep-5Hz-lm-0.6B'). Default from ACESTEP_LM_MODEL_PATH.",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        default=env_bool("ACESTEP_NO_INIT", False),
        help="Skip model loading at startup (models will be lazy-loaded on first request). "
        "Can also be set via ACESTEP_NO_INIT=true environment variable.",
    )
    args = parser.parse_args(args=argv)

    api_key = (args.api_key or "").strip() or None
    if api_key is not None:
        os.environ["ACESTEP_API_KEY"] = api_key
    else:
        os.environ.pop("ACESTEP_API_KEY", None)

    if not _is_loopback_host(str(args.host)) and api_key is None:
        parser.error(
            "Refusing to bind an unauthenticated API beyond loopback. "
            "Set --api-key (or ACESTEP_API_KEY) or bind to 127.0.0.1/::1/localhost."
        )

    if args.download_source and args.download_source != "auto":
        os.environ["ACESTEP_DOWNLOAD_SOURCE"] = args.download_source
        print(f"Using preferred download source: {args.download_source}")

    if args.init_llm:
        os.environ["ACESTEP_INIT_LLM"] = "true"
        print("[API Server] LLM initialization enabled via --init-llm")

    if args.lm_model_path:
        os.environ["ACESTEP_LM_MODEL_PATH"] = args.lm_model_path
        print(f"[API Server] Using LM model: {args.lm_model_path}")

    if args.no_init:
        os.environ["ACESTEP_NO_INIT"] = "true"
        print("[API Server] --no-init: Models will NOT be loaded at startup (lazy load on first request)")

    application = _resolve_app_factory(app_factory)()

    # IMPORTANT: in-memory queue/store -> workers MUST be 1
    uvicorn.run(
        application,
        host=str(args.host),
        port=int(args.port),
        reload=False,
        workers=1,
    )
