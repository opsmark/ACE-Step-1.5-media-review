"""Focused security tests for API-selected model identifiers."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from acestep.api import model_download
from acestep.api.http.model_init_service import initialize_models_for_request
from acestep.api.model_registry import (
    MODEL_REPO_MAPPING,
    ModelSelectionError,
    approved_model_ids,
    normalize_model_identifier,
    resolve_model_directory,
)
from acestep.api.runtime_helpers import temporary_llm_model


class ModelRegistryTests(TestCase):
    def test_registered_identifier_is_accepted(self) -> None:
        self.assertEqual(
            "acestep-v15-turbo",
            normalize_model_identifier(
                "  acestep-v15-turbo  ",
                allowed_ids=approved_model_ids(),
            ),
        )

    def test_paths_control_characters_and_unknown_names_are_rejected(self) -> None:
        cases = [
            "/tmp/model",
            r"C:\models\x",
            "../model",
            "group/model",
            r"group\model",
            ".",
            "..",
            "unknown-model",
            "bad\x00name",
        ]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ModelSelectionError):
                    normalize_model_identifier(
                        value,
                        allowed_ids=approved_model_ids(),
                    )

    def test_operator_local_id_is_exact_and_local_only(self) -> None:
        with patch.dict(
            os.environ,
            {"ACESTEP_LOCAL_MODEL_IDS": "local-model"},
            clear=False,
        ):
            self.assertIn("local-model", approved_model_ids())
            self.assertNotIn("local-model", MODEL_REPO_MAPPING)

    def test_invalid_operator_registry_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            {"ACESTEP_LOCAL_MODEL_IDS": "../escape"},
            clear=False,
        ):
            with self.assertRaises(ModelSelectionError):
                approved_model_ids()

    def test_symlink_escape_is_rejected_after_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, Path(root) / "acestep-v15-turbo")
            with self.assertRaises(ModelSelectionError):
                resolve_model_directory(root, "acestep-v15-turbo")

    def test_contained_model_directory_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            expected = Path(root) / "acestep-v15-turbo"
            expected.mkdir()
            self.assertEqual(
                os.path.normcase(os.path.realpath(expected)),
                resolve_model_directory(root, "acestep-v15-turbo"),
            )


class ModelDownloadTests(TestCase):
    def test_unknown_model_never_inherits_default_repo(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ModelSelectionError):
                model_download.ensure_model_downloaded("unknown-model", root)

    def test_configured_local_model_must_exist_and_never_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(
                os.environ,
                {"ACESTEP_LOCAL_MODEL_IDS": "local-model"},
                clear=False,
            ):
                with patch.object(
                    model_download,
                    "download_from_huggingface",
                ) as huggingface, patch.object(
                    model_download,
                    "download_from_modelscope",
                ) as modelscope:
                    with self.assertRaises(ModelSelectionError):
                        model_download.ensure_model_downloaded("local-model", root)
                    huggingface.assert_not_called()
                    modelscope.assert_not_called()

                    model_dir = Path(root) / "local-model"
                    model_dir.mkdir()
                    (model_dir / "config.json").write_text("{}", encoding="utf-8")
                    self.assertEqual(
                        os.path.normcase(os.path.realpath(model_dir)),
                        model_download.ensure_model_downloaded("local-model", root),
                    )
                    huggingface.assert_not_called()
                    modelscope.assert_not_called()

    def test_provider_result_is_re_resolved_and_must_be_nonempty(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            def fake_download(_repo, local_dir, model_id):
                model_dir = Path(local_dir) / model_id
                model_dir.mkdir()
                (model_dir / "config.json").write_text("{}", encoding="utf-8")
                return str(model_dir)

            with patch.dict(
                os.environ,
                {"ACESTEP_DOWNLOAD_SOURCE": "huggingface"},
                clear=False,
            ), patch.object(
                model_download,
                "download_from_huggingface",
                side_effect=fake_download,
            ), patch.object(
                model_download,
                "download_from_modelscope",
            ) as modelscope:
                result = model_download.ensure_model_downloaded(
                    "acestep-v15-base",
                    root,
                )
                self.assertEqual(
                    os.path.normcase(
                        os.path.realpath(Path(root) / "acestep-v15-base")
                    ),
                    result,
                )
                modelscope.assert_not_called()

    def test_provider_cannot_replace_model_with_escape_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            def fake_download(_repo, local_dir, model_id):
                os.symlink(outside, Path(local_dir) / model_id)
                return str(Path(local_dir) / model_id)

            with patch.dict(
                os.environ,
                {"ACESTEP_DOWNLOAD_SOURCE": "huggingface"},
                clear=False,
            ), patch.object(
                model_download,
                "download_from_huggingface",
                side_effect=fake_download,
            ):
                with self.assertRaises(ModelSelectionError):
                    model_download.ensure_model_downloaded(
                        "acestep-v15-base",
                        root,
                    )


class ModelInitTests(TestCase):
    @staticmethod
    def _get_model_name(value):
        return os.path.basename(str(value or "").rstrip("/\\"))

    @staticmethod
    def _env_bool(_name, default):
        return default

    @staticmethod
    def _state():
        handler = MagicMock()
        handler.initialize_service.return_value = ("ok", True)
        llm = MagicMock()
        llm.initialize.return_value = ("ok", True)
        return SimpleNamespace(
            handler=handler,
            llm_handler=llm,
            _config_path="acestep-v15-turbo",
            _llm_init_lock=MagicMock(),
        )

    def test_absolute_api_model_path_is_rejected_before_download_or_load(self) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as root:
            ensure = MagicMock()
            with self.assertRaises(ModelSelectionError):
                initialize_models_for_request(
                    app_state=state,
                    model_name="/tmp/acestep-v15-base",
                    init_llm=False,
                    requested_lm_model_path=None,
                    get_project_root=lambda: root,
                    get_model_name=self._get_model_name,
                    ensure_model_downloaded=ensure,
                    env_bool=self._env_bool,
                )
            ensure.assert_not_called()
            state.handler.initialize_service.assert_not_called()

    def test_unknown_api_lm_is_rejected_without_poisoning_environment(self) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ,
            {"ACESTEP_LM_MODEL_PATH": "acestep-5Hz-lm-0.6B"},
            clear=False,
        ):
            ensure = MagicMock()
            with self.assertRaises(ModelSelectionError):
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=True,
                    requested_lm_model_path="../../evil-lm",
                    get_project_root=lambda: root,
                    get_model_name=self._get_model_name,
                    ensure_model_downloaded=ensure,
                    env_bool=self._env_bool,
                )
            self.assertEqual(
                "acestep-5Hz-lm-0.6B",
                os.environ["ACESTEP_LM_MODEL_PATH"],
            )
            state.llm_handler.initialize.assert_not_called()

    def test_registered_models_are_normalized_before_load(self) -> None:
        state = self._state()
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        state._llm_init_lock = lock
        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            ensure = MagicMock()
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=True,
                requested_lm_model_path="acestep-5Hz-lm-0.6B",
                get_project_root=lambda: root,
                get_model_name=self._get_model_name,
                ensure_model_downloaded=ensure,
                env_bool=self._env_bool,
            )
            checkpoint_dir = str(Path(root) / "checkpoints")
            self.assertEqual(
                [
                    ("acestep-v15-base", checkpoint_dir),
                    ("vae", checkpoint_dir),
                    ("acestep-5Hz-lm-0.6B", checkpoint_dir),
                ],
                [call.args for call in ensure.call_args_list],
            )
            self.assertEqual(
                "acestep-5Hz-lm-0.6B",
                os.environ["ACESTEP_LM_MODEL_PATH"],
            )
            state.handler.initialize_service.assert_called_once()
            state.llm_handler.initialize.assert_called_once()
            self.assertEqual("acestep-v15-base", result["loaded_model"])
            self.assertEqual(
                "acestep-5Hz-lm-0.6B",
                result["loaded_lm_model"],
            )


class TemporaryModelTests(TestCase):
    @staticmethod
    def _get_model_name(value):
        return os.path.basename(str(value or "").rstrip("/\\"))

    def test_invalid_temporary_model_fails_before_download_or_switch(self) -> None:
        app = SimpleNamespace(state=SimpleNamespace(_llm_init_lock=MagicMock()))
        llm = MagicMock(llm_initialized=True)
        ensure = MagicMock()
        with self.assertRaises(ModelSelectionError):
            with temporary_llm_model(
                app,
                llm,
                "/tmp/acestep-5Hz-lm-0.6B",
                get_project_root=lambda: "/tmp/project",
                get_model_name=self._get_model_name,
                ensure_model_downloaded=ensure,
                env_bool=lambda _name, default: default,
            ):
                pass
        ensure.assert_not_called()
        llm.initialize.assert_not_called()

    def test_download_failure_is_not_swallowed_before_loader(self) -> None:
        lock = MagicMock()
        lock.__enter__ = MagicMock(return_value=None)
        lock.__exit__ = MagicMock(return_value=False)
        app = SimpleNamespace(state=SimpleNamespace(_llm_init_lock=lock))
        llm = MagicMock(
            llm_initialized=True,
            last_init_params={"lm_model_path": "acestep-5Hz-lm-1.7B"},
        )
        ensure = MagicMock(side_effect=RuntimeError("provider failed"))
        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            with temporary_llm_model(
                app,
                llm,
                "acestep-5Hz-lm-0.6B",
                get_project_root=lambda: "/tmp/project",
                get_model_name=self._get_model_name,
                ensure_model_downloaded=ensure,
                env_bool=lambda _name, default: default,
            ):
                pass
        llm.initialize.assert_not_called()
