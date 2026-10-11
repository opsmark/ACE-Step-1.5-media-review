"""Security tests for repository-owned model code loading."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from acestep.api.trusted_model_loader import (
    ModelCodePolicyError,
    TRUSTED_DIT_VARIANTS,
    inspect_causal_lm_checkpoint,
    inspect_dit_checkpoint,
    load_trusted_causal_lm,
    load_trusted_dit_model,
)


class _RecordingConfig:
    calls = []

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))
        return {"fixture": "config"}


class _RecordingModel:
    calls = []

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))
        return {"fixture": "model"}


class TrustedModelLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingConfig.calls.clear()
        _RecordingModel.calls.clear()

    @staticmethod
    def make_checkpoint(
        root: str,
        model_id: str,
        *,
        auto_map=None,
        architectures=None,
        include_weights: bool = True,
    ) -> Path:
        checkpoint = Path(root) / model_id
        checkpoint.mkdir()
        payload = {}
        if auto_map is not None:
            payload["auto_map"] = auto_map
        if architectures is not None:
            payload["architectures"] = architectures
        (checkpoint / "config.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        if include_weights:
            (checkpoint / "model.safetensors").write_bytes(b"fixture")
        return checkpoint

    def test_variant_registry_matches_maintained_model_code_ownership(self) -> None:
        self.assertEqual(
            {
                "acestep-v15-turbo": "turbo",
                "acestep-v15-sft": "sft",
                "acestep-v15-base": "base",
                "acestep-v15-base-sft-fix-inst": "sft",
                "acestep-v15-turbo-shift1": "turbo",
                "acestep-v15-turbo-shift3": "turbo",
                "acestep-v15-turbo-continuous": "turbo",
                "acestep-v15-turbo-fix-inst-shift3": "turbo",
                "acestep-v15-turbo-fix-inst-shift-continuous": "turbo",
                "acestep-v15-turbo-fix-inst-shift-dynamic": "turbo",
                "acestep-v15-turbo-rl": "turbo",
                "acestep-v15-xl-base": "xl_base",
                "acestep-v15-xl-sft": "xl_sft",
                "acestep-v15-xl-turbo": "xl_turbo",
            },
            dict(TRUSTED_DIT_VARIANTS),
        )

    def test_known_dit_contract_accepts_repository_auto_map(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(
                root,
                "acestep-v15-turbo",
                auto_map={
                    "AutoConfig": "configuration_acestep_v15.AceStepConfig",
                    "AutoModel": (
                        "modeling_acestep_v15_turbo."
                        "AceStepConditionGenerationModel"
                    ),
                },
                architectures=["AceStepConditionGenerationModel"],
            )
            contract = inspect_dit_checkpoint(
                str(checkpoint),
                model_id="acestep-v15-turbo",
            )
            self.assertEqual("turbo", contract.variant)
            self.assertEqual(1, len(contract.weight_files))

    def test_absent_auto_map_is_data_only_and_allowed_for_known_id(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(
                root,
                "acestep-v15-base",
                architectures=["AceStepConditionGenerationModel"],
            )
            self.assertEqual(
                "base",
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-base",
                ).variant,
            )

    def test_unexpected_auto_map_or_architecture_is_rejected(self) -> None:
        cases = [
            (
                {"AutoModel": "evil_module.EvilModel"},
                ["AceStepConditionGenerationModel"],
            ),
            (None, ["OtherModel"]),
        ]
        for auto_map, architectures in cases:
            with self.subTest(auto_map=auto_map, architectures=architectures):
                with tempfile.TemporaryDirectory() as root:
                    checkpoint = self.make_checkpoint(
                        root,
                        "acestep-v15-base",
                        auto_map=auto_map,
                        architectures=architectures,
                    )
                    with self.assertRaises(ModelCodePolicyError):
                        inspect_dit_checkpoint(
                            str(checkpoint),
                            model_id="acestep-v15-base",
                        )

    def test_unknown_or_mismatched_model_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(root, "acestep-v15-base")
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(str(checkpoint), model_id="unknown")
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-turbo",
                )

    def test_config_weights_and_checkpoint_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside)
            (outside_path / "config.json").write_text("{}", encoding="utf-8")
            (outside_path / "model.safetensors").write_bytes(b"fixture")
            checkpoint = Path(root) / "acestep-v15-base"
            checkpoint.symlink_to(outside_path, target_is_directory=True)
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-base",
                )

        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            checkpoint = Path(root) / "acestep-v15-base"
            checkpoint.mkdir()
            (Path(outside) / "config.json").write_text("{}", encoding="utf-8")
            (checkpoint / "config.json").symlink_to(Path(outside) / "config.json")
            (checkpoint / "model.safetensors").write_bytes(b"fixture")
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-base",
                )

    def test_pickle_only_weights_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(
                root,
                "acestep-v15-base",
                include_weights=False,
            )
            (checkpoint / "pytorch_model.bin").write_bytes(b"not-executed")
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-base",
                )

    def test_dit_loader_imports_fixed_application_modules_and_safe_kwargs(self) -> None:
        imported = []

        def importer(name: str):
            imported.append(name)
            if name.endswith("configuration_acestep_v15"):
                return SimpleNamespace(AceStepConfig=_RecordingConfig)
            return SimpleNamespace(AceStepConditionGenerationModel=_RecordingModel)

        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(root, "acestep-v15-xl-turbo")
            result = load_trusted_dit_model(
                str(checkpoint),
                model_id="acestep-v15-xl-turbo",
                attn_implementation="sdpa",
                dtype="fixture-dtype",
                importer=importer,
            )

        self.assertEqual({"fixture": "model"}, result)
        self.assertEqual(
            [
                "acestep.models.xl_turbo.configuration_acestep_v15",
                "acestep.models.xl_turbo.modeling_acestep_v15_xl_turbo",
            ],
            imported,
        )
        self.assertEqual(True, _RecordingConfig.calls[0][1]["local_files_only"])
        model_kwargs = _RecordingModel.calls[0][1]
        self.assertEqual(_RecordingConfig.calls[0][0][0], _RecordingModel.calls[0][0][0])
        self.assertEqual({"fixture": "config"}, model_kwargs["config"])
        self.assertTrue(model_kwargs["local_files_only"])
        self.assertTrue(model_kwargs["use_safetensors"])
        self.assertEqual("sdpa", model_kwargs["attn_implementation"])
        self.assertNotIn("trust_remote_code", model_kwargs)

    def test_lm_custom_code_is_rejected_and_standard_loader_forces_safe_flags(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(
                root,
                "acestep-5Hz-lm-0.6B",
                auto_map={"AutoModelForCausalLM": "evil.CustomLM"},
            )
            with self.assertRaises(ModelCodePolicyError):
                inspect_causal_lm_checkpoint(str(checkpoint))

        with tempfile.TemporaryDirectory() as root:
            checkpoint = self.make_checkpoint(root, "acestep-5Hz-lm-0.6B")
            result = load_trusted_causal_lm(
                str(checkpoint),
                auto_model_class=_RecordingModel,
            )
        self.assertEqual({"fixture": "model"}, result)
        kwargs = _RecordingModel.calls[0][1]
        self.assertFalse(kwargs["trust_remote_code"])
        self.assertTrue(kwargs["local_files_only"])
        self.assertTrue(kwargs["use_safetensors"])

    def test_large_or_invalid_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            checkpoint = Path(root) / "acestep-v15-base"
            checkpoint.mkdir()
            (checkpoint / "config.json").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
            (checkpoint / "model.safetensors").write_bytes(b"fixture")
            with self.assertRaises(ModelCodePolicyError):
                inspect_dit_checkpoint(
                    str(checkpoint),
                    model_id="acestep-v15-base",
                )

    def test_runtime_sources_use_trusted_helpers_after_candidate_build(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        dit_source = (
            repository
            / "acestep/core/generation/handler/init_service_loader.py"
        ).read_text(encoding="utf-8")
        lm_source = (repository / "acestep/llm_inference.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("load_trusted_dit_model", dit_source)
        self.assertNotIn("trust_remote_code=True", dit_source)
        self.assertIn("load_trusted_causal_lm", lm_source)
        self.assertNotIn("trust_remote_code=True", lm_source)
        self.assertNotIn(
            "AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)",
            lm_source,
        )
        self.assertIn("local_files_only=True", lm_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
