"""OpenRouter package initialization and direct-module launch guard."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

from acestep.network_exposure import validate_api_exposure

_DIRECT_SERVER_MODULE = "openrouter.openrouter_api_server"


def _direct_server_arguments(orig_argv: Sequence[str]) -> list[str] | None:
    """Return arguments for ``python -m openrouter.openrouter_api_server``."""

    values = list(orig_argv)
    try:
        module_index = values.index("-m")
    except ValueError:
        return None
    if module_index + 1 >= len(values):
        return None
    if values[module_index + 1] != _DIRECT_SERVER_MODULE:
        return None
    return values[module_index + 2 :]


def _apply_direct_module_guard(
    orig_argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Validate/publish direct-module auth before the server module imports.

    ``openrouter.openrouter_api_server`` historically creates a global FastAPI
    app during import. Since Python imports this package first for ``-m``
    execution, this narrow guard can reject an unsafe bind and publish the CLI
    key before that global application is constructed. Other package imports
    and the new ``openrouter.secure_server`` entrypoint are unaffected.
    """

    argv = sys.orig_argv if orig_argv is None else orig_argv
    module_args = _direct_server_arguments(argv)
    if module_args is None:
        return

    environment = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--host",
        default=environment.get("OPENROUTER_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--api-key",
        default=environment.get("OPENROUTER_API_KEY"),
    )
    parsed, _unknown = parser.parse_known_args(module_args)
    api_key = str(parsed.api_key or "").strip() or None
    validate_api_exposure(str(parsed.host), api_key, service="OpenRouter API")

    # The production call always receives os.environ. MutableMapping is avoided
    # in the public annotation only to keep the injectable test contract small.
    if api_key is not None:
        os.environ["OPENROUTER_API_KEY"] = api_key
    else:
        os.environ.pop("OPENROUTER_API_KEY", None)


_apply_direct_module_guard()
