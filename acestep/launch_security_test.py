"""Focused tests for official ACE-Step launch boundary enforcement."""

from __future__ import annotations

import os
import sys
from unittest import TestCase
from unittest.mock import MagicMock, patch

from acestep.network_exposure import (
    ExposurePolicyError,
    GradioExposure,
    is_loopback_host,
    validate_api_exposure,
    validate_gradio_exposure,
)
from acestep.secure_gradio_entrypoint import (
    main as gradio_main,
    prepare_gradio_arguments,
)
from openrouter import _apply_direct_module_guard, _direct_server_arguments
from openrouter.secure_server import main as openrouter_main


class ExposurePolicyTests(TestCase):
    def test_loopback_variants(self) -> None:
        for host in ("127.0.0.1", "127.1.2.3", "::1", "localhost"):
            self.assertTrue(is_loopback_host(host), host)
        for host in ("0.0.0.0", "::", "192.168.1.2", "example.test"):
            self.assertFalse(is_loopback_host(host), host)

    def test_remote_api_requires_key(self) -> None:
        with self.assertRaises(ExposurePolicyError):
            validate_api_exposure("0.0.0.0", None, service="test")
        validate_api_exposure("0.0.0.0", "secret", service="test")
        validate_api_exposure("127.0.0.1", None, service="test")

    def test_gradio_remote_and_share_require_credentials(self) -> None:
        for config in (
            GradioExposure("0.0.0.0", False, None, None, False, None),
            GradioExposure("127.0.0.1", True, None, None, False, None),
        ):
            with self.subTest(config=config):
                with self.assertRaises(ExposurePolicyError):
                    validate_gradio_exposure(config)

    def test_partial_gradio_credentials_are_rejected_even_on_loopback(self) -> None:
        with self.assertRaises(ExposurePolicyError):
            validate_gradio_exposure(
                GradioExposure("127.0.0.1", False, "user", None, False, None)
            )

    def test_loopback_proxy_boundary_allows_ui_but_not_keyless_api(self) -> None:
        validate_gradio_exposure(
            GradioExposure(
                "0.0.0.0",
                False,
                None,
                None,
                False,
                None,
                trusted_proxy_boundary=True,
                proxy_bind_address="127.0.0.1",
            )
        )
        with self.assertRaises(ExposurePolicyError):
            validate_gradio_exposure(
                GradioExposure(
                    "0.0.0.0",
                    False,
                    None,
                    None,
                    True,
                    None,
                    trusted_proxy_boundary=True,
                    proxy_bind_address="127.0.0.1",
                )
            )


class GradioEntrypointTests(TestCase):
    def test_remote_env_credentials_are_injected(self) -> None:
        prepared = prepare_gradio_arguments(
            ["--server-name", "0.0.0.0"],
            {
                "ACESTEP_GRADIO_USERNAME": "user",
                "ACESTEP_GRADIO_PASSWORD": "pass",
            },
        )
        self.assertEqual("user", prepared[prepared.index("--auth-username") + 1])
        self.assertEqual("pass", prepared[prepared.index("--auth-password") + 1])

    def test_remote_without_credentials_is_rejected_before_pipeline_import(self) -> None:
        pipeline = MagicMock()
        with self.assertRaises(ExposurePolicyError):
            gradio_main(
                ["--server-name", "0.0.0.0"],
                environ={},
                pipeline_main=pipeline,
            )
        pipeline.assert_not_called()

    def test_prepared_arguments_are_delegated_and_sys_argv_restored(self) -> None:
        observed: dict[str, list[str]] = {}
        original = list(sys.argv)

        def pipeline() -> None:
            observed["argv"] = list(sys.argv)

        gradio_main([], environ={}, pipeline_main=pipeline)
        self.assertEqual("127.0.0.1", observed["argv"][-1])
        self.assertEqual(original, sys.argv)


class OpenRouterEntrypointTests(TestCase):
    def test_remote_without_key_is_rejected_before_app_creation(self) -> None:
        factory = MagicMock()
        runner = MagicMock()
        with self.assertRaises(ExposurePolicyError):
            openrouter_main(
                ["--host", "0.0.0.0"],
                app_factory=factory,
                uvicorn_run=runner,
            )
        factory.assert_not_called()
        runner.assert_not_called()

    def test_key_is_visible_before_app_creation(self) -> None:
        observed: dict[str, str | None] = {}
        application = object()

        def factory():
            observed["key"] = os.getenv("OPENROUTER_API_KEY")
            return application

        runner = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            openrouter_main(
                ["--host", "0.0.0.0", "--port", "9002", "--api-key", " secret "],
                app_factory=factory,
                uvicorn_run=runner,
            )
        self.assertEqual("secret", observed["key"])
        runner.assert_called_once_with(
            application,
            host="0.0.0.0",
            port=9002,
            reload=False,
            workers=1,
        )

    def test_loopback_without_key_remains_supported_and_clears_stale_key(self) -> None:
        runner = MagicMock()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "stale"}, clear=True):
            openrouter_main(
                ["--host", "127.0.0.1", "--api-key", ""],
                app_factory=lambda: object(),
                uvicorn_run=runner,
            )
            self.assertNotIn("OPENROUTER_API_KEY", os.environ)
        runner.assert_called_once()


class DirectModuleGuardTests(TestCase):
    def test_only_historical_server_module_is_intercepted(self) -> None:
        self.assertEqual(
            ["--host", "0.0.0.0"],
            _direct_server_arguments(
                [
                    "python",
                    "-m",
                    "openrouter.openrouter_api_server",
                    "--host",
                    "0.0.0.0",
                ]
            ),
        )
        self.assertIsNone(
            _direct_server_arguments(
                ["python", "-m", "openrouter.secure_server", "--host", "0.0.0.0"]
            )
        )

    def test_direct_remote_module_without_key_is_rejected_before_import(self) -> None:
        with self.assertRaises(ExposurePolicyError):
            _apply_direct_module_guard(
                [
                    "python",
                    "-m",
                    "openrouter.openrouter_api_server",
                    "--host",
                    "0.0.0.0",
                ],
                {},
            )

    def test_direct_remote_module_publishes_key_before_import(self) -> None:
        environment: dict[str, str] = {}
        _apply_direct_module_guard(
            [
                "python",
                "-m",
                "openrouter.openrouter_api_server",
                "--host",
                "0.0.0.0",
                "--api-key",
                " secret ",
            ],
            environment,
        )
        self.assertEqual("secret", environment["OPENROUTER_API_KEY"])

    def test_direct_loopback_empty_key_clears_stale_environment(self) -> None:
        environment = {"OPENROUTER_API_KEY": "stale"}
        _apply_direct_module_guard(
            [
                "python",
                "-m",
                "openrouter.openrouter_api_server",
                "--host",
                "127.0.0.1",
                "--api-key",
                "",
            ],
            environment,
        )
        self.assertNotIn("OPENROUTER_API_KEY", environment)
