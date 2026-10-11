"""Focused security tests for runtime helper process exposure."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from acestep.api.runtime_helpers import _tensorboard_loopback_host, start_tensorboard


class TensorBoardSecurityTests(TestCase):
    def test_default_launch_binds_loopback_and_never_bind_all(self) -> None:
        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=None))
        process = MagicMock()
        with patch.dict(os.environ, {}, clear=True), patch(
            "acestep.api.runtime_helpers.subprocess.Popen",
            return_value=process,
        ) as popen:
            url = start_tensorboard(
                app,
                "/tmp/logs",
                stop_tensorboard_fn=MagicMock(),
            )

        argv = popen.call_args.args[0]
        self.assertIn("--host", argv)
        self.assertEqual("127.0.0.1", argv[argv.index("--host") + 1])
        self.assertNotIn("--bind_all", argv)
        self.assertEqual("http://127.0.0.1:6006", url)
        self.assertIs(process, app.state.tensorboard_process)

    def test_ipv6_loopback_is_supported_and_url_is_bracketed(self) -> None:
        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=None))
        with patch.dict(
            os.environ,
            {"TENSORBOARD_HOST": "::1"},
            clear=True,
        ), patch(
            "acestep.api.runtime_helpers.subprocess.Popen",
            return_value=MagicMock(),
        ):
            self.assertEqual(
                "http://[::1]:6006",
                start_tensorboard(
                    app,
                    "/tmp/logs",
                    stop_tensorboard_fn=MagicMock(),
                ),
            )

    def test_remote_host_is_rejected_before_process_start(self) -> None:
        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=None))
        with patch.dict(
            os.environ,
            {"TENSORBOARD_HOST": "0.0.0.0"},
            clear=True,
        ), patch(
            "acestep.api.runtime_helpers.subprocess.Popen",
        ) as popen:
            self.assertIsNone(
                start_tensorboard(
                    app,
                    "/tmp/logs",
                    stop_tensorboard_fn=MagicMock(),
                )
            )
        popen.assert_not_called()

    def test_helper_rejects_non_loopback_hostname(self) -> None:
        with patch.dict(
            os.environ,
            {"TENSORBOARD_HOST": "example.test"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                _tensorboard_loopback_host()
