"""Unit tests for secure API server CLI bootstrap."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from acestep.api.server_cli import _is_loopback_host, run_api_server_main


class ServerCliTests(unittest.TestCase):
    """Behavior tests for argument parsing, auth ordering, and uvicorn wiring."""

    @staticmethod
    def _env_bool(_name: str, default: bool) -> bool:
        return default

    def test_run_api_server_main_invokes_uvicorn_with_parsed_host_port(self) -> None:
        """CLI helper should pass parsed host/port and fixed worker settings to uvicorn."""

        application = object()
        app_factory = MagicMock(return_value=application)

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run") as mock_run:
                run_api_server_main(
                    self._env_bool,
                    argv=[
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "9001",
                        "--api-key",
                        "secret",
                    ],
                    app_factory=app_factory,
                )

        app_factory.assert_called_once_with()
        mock_run.assert_called_once_with(
            application,
            host="0.0.0.0",
            port=9001,
            reload=False,
            workers=1,
        )

    def test_run_api_server_main_sets_env_overrides_from_flags(self) -> None:
        """CLI helper should apply legacy env side effects for supported flags."""

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run"):
                run_api_server_main(
                    self._env_bool,
                    argv=[
                        "--api-key",
                        "secret",
                        "--download-source",
                        "huggingface",
                        "--init-llm",
                        "--lm-model-path",
                        "acestep-5Hz-lm-0.6B",
                        "--no-init",
                    ],
                    app_factory=MagicMock(return_value=object()),
                )

            self.assertEqual("secret", os.environ.get("ACESTEP_API_KEY"))
            self.assertEqual("huggingface", os.environ.get("ACESTEP_DOWNLOAD_SOURCE"))
            self.assertEqual("true", os.environ.get("ACESTEP_INIT_LLM"))
            self.assertEqual("acestep-5Hz-lm-0.6B", os.environ.get("ACESTEP_LM_MODEL_PATH"))
            self.assertEqual("true", os.environ.get("ACESTEP_NO_INIT"))

    def test_run_api_server_main_uses_env_bool_for_flag_defaults(self) -> None:
        """CLI helper should respect env_bool-provided defaults when flags omitted."""

        observed = []

        def _env_bool(name: str, default: bool) -> bool:
            observed.append((name, default))
            if name == "ACESTEP_INIT_LLM":
                return True
            return False

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run") as mock_run:
                run_api_server_main(
                    _env_bool,
                    argv=[],
                    app_factory=MagicMock(return_value=object()),
                )
                self.assertEqual("true", os.environ.get("ACESTEP_INIT_LLM"))
                self.assertIsNone(os.environ.get("ACESTEP_NO_INIT"))
                mock_run.assert_called_once()

        self.assertIn(("ACESTEP_INIT_LLM", False), observed)
        self.assertIn(("ACESTEP_NO_INIT", False), observed)

    def test_loopback_detection(self) -> None:
        self.assertTrue(_is_loopback_host("127.0.0.1"))
        self.assertTrue(_is_loopback_host("::1"))
        self.assertTrue(_is_loopback_host("localhost"))
        self.assertFalse(_is_loopback_host("0.0.0.0"))
        self.assertFalse(_is_loopback_host("192.168.1.10"))
        self.assertFalse(_is_loopback_host("example.test"))

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_remote_bind_without_key_is_rejected_before_app_creation(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        app_factory = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as raised:
                run_api_server_main(
                    self._env_bool,
                    argv=["--host", "0.0.0.0"],
                    app_factory=app_factory,
                )

        self.assertEqual(raised.exception.code, 2)
        app_factory.assert_not_called()
        uvicorn_run.assert_not_called()

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_api_key_is_visible_when_fresh_app_is_created(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        application = object()
        observed = {}

        def app_factory():
            observed["api_key"] = os.getenv("ACESTEP_API_KEY")
            return application

        with patch.dict(os.environ, {}, clear=True):
            run_api_server_main(
                self._env_bool,
                argv=[
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "9001",
                    "--api-key",
                    "  secret-value  ",
                ],
                app_factory=app_factory,
            )

        self.assertEqual(observed["api_key"], "secret-value")
        uvicorn_run.assert_called_once_with(
            application,
            host="0.0.0.0",
            port=9001,
            reload=False,
            workers=1,
        )

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_loopback_without_key_remains_supported(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        application = object()
        app_factory = MagicMock(return_value=application)

        with patch.dict(os.environ, {"ACESTEP_API_KEY": "stale"}, clear=True):
            run_api_server_main(
                self._env_bool,
                argv=["--host", "127.0.0.1", "--api-key", ""],
                app_factory=app_factory,
            )
            self.assertNotIn("ACESTEP_API_KEY", os.environ)

        app_factory.assert_called_once_with()
        uvicorn_run.assert_called_once_with(
            application,
            host="127.0.0.1",
            port=8001,
            reload=False,
            workers=1,
        )


if __name__ == "__main__":
    unittest.main()
