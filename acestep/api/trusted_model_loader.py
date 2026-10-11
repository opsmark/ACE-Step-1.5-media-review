"""Load model data through repository-owned implementations only.

This module treats checkpoint configuration and tensor files as data. API model
selectors may choose only a reviewed model identifier; the selected checkpoint
must not supply Python modules through Transformers ``trust_remote_code``.
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

_MAX_CONFIG_BYTES = 2 * 1024 * 1024
_CONFIG_CLASS = "AceStepConfig"
_MODEL_CLASS = "AceStepConditionGenerationModel"

# Mirrors the maintained model_downloader variant ownership. The import target
# is always application source in this repository, never Python copied into or
# downloaded beside checkpoint tensors.
TRUSTED_DIT_VARIANTS: Mapping[str, str] = {
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
}

_VARIANT_MODEL_FILES: Mapping[str, str] = {
    "base": "modeling_acestep_v15_base",
    "sft": "modeling_acestep_v15_base",
    "turbo": "modeling_acestep_v15_turbo",
    "xl_base": "modeling_acestep_v15_xl_base",
    "xl_sft": "modeling_acestep_v15_xl_base",
    "xl_turbo": "modeling_acestep_v15_xl_turbo",
}


class ModelCodePolicyError(ValueError):
    """Raised when checkpoint data requests unapproved executable code."""


@dataclass(frozen=True)
class CheckpointContract:
    model_id: str
    variant: str
    checkpoint_path: str
    config_path: str
    weight_files: tuple[str, ...]


def _regular_nonlink_file(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise ModelCodePolicyError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise ModelCodePolicyError(f"{label} is not a regular file: {path}")


def _read_config(checkpoint: Path) -> tuple[Path, dict[str, Any]]:
    config_path = checkpoint / "config.json"
    _regular_nonlink_file(config_path, label="Checkpoint config")
    size = config_path.stat().st_size
    if size <= 0 or size > _MAX_CONFIG_BYTES:
        raise ModelCodePolicyError(
            f"Checkpoint config size is outside the allowed range: {size} bytes"
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelCodePolicyError(f"Checkpoint config is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModelCodePolicyError("Checkpoint config must be a JSON object")
    return config_path, payload


def _safetensor_files(checkpoint: Path) -> tuple[str, ...]:
    files = []
    for path in sorted(checkpoint.glob("*.safetensors")):
        _regular_nonlink_file(path, label="Checkpoint tensor file")
        files.append(str(path))
    if not files:
        raise ModelCodePolicyError(
            "Checkpoint has no top-level safetensors weights; pickle-capable weight fallback is refused"
        )
    return tuple(files)


def _expected_auto_map(variant: str) -> dict[str, str]:
    model_file = _VARIANT_MODEL_FILES[variant]
    return {
        "AutoConfig": f"configuration_acestep_v15.{_CONFIG_CLASS}",
        "AutoModel": f"{model_file}.{_MODEL_CLASS}",
    }


def inspect_dit_checkpoint(
    checkpoint_path: str,
    *,
    model_id: str,
) -> CheckpointContract:
    """Validate one DiT checkpoint as data for an application-owned class."""

    variant = TRUSTED_DIT_VARIANTS.get(model_id)
    if variant is None:
        raise ModelCodePolicyError(f"No repository-owned implementation for {model_id!r}")

    checkpoint = Path(checkpoint_path)
    if checkpoint.is_symlink():
        raise ModelCodePolicyError(f"Checkpoint directory must not be a symlink: {checkpoint}")
    if not checkpoint.is_dir():
        raise ModelCodePolicyError(f"Checkpoint directory does not exist: {checkpoint}")
    if checkpoint.name != model_id:
        raise ModelCodePolicyError(
            f"Checkpoint directory name {checkpoint.name!r} does not match model ID {model_id!r}"
        )

    config_path, payload = _read_config(checkpoint)
    auto_map = payload.get("auto_map")
    if auto_map is not None:
        if not isinstance(auto_map, dict) or auto_map != _expected_auto_map(variant):
            raise ModelCodePolicyError(
                "Checkpoint auto_map does not match the repository-owned implementation contract"
            )

    architectures = payload.get("architectures")
    if architectures is not None:
        if not isinstance(architectures, list) or architectures != [_MODEL_CLASS]:
            raise ModelCodePolicyError(
                f"Checkpoint architectures must be exactly [{_MODEL_CLASS!r}]"
            )

    weights = _safetensor_files(checkpoint)
    return CheckpointContract(
        model_id=model_id,
        variant=variant,
        checkpoint_path=str(checkpoint),
        config_path=str(config_path),
        weight_files=weights,
    )


def inspect_causal_lm_checkpoint(checkpoint_path: str) -> tuple[str, tuple[str, ...]]:
    """Reject any LM checkpoint that advertises executable custom code."""

    checkpoint = Path(checkpoint_path)
    if checkpoint.is_symlink():
        raise ModelCodePolicyError(f"LM checkpoint directory must not be a symlink: {checkpoint}")
    if not checkpoint.is_dir():
        raise ModelCodePolicyError(f"LM checkpoint directory does not exist: {checkpoint}")
    config_path, payload = _read_config(checkpoint)
    if payload.get("auto_map"):
        raise ModelCodePolicyError(
            "LM checkpoint advertises custom code through auto_map; only standard Transformers classes are allowed"
        )
    return str(config_path), _safetensor_files(checkpoint)


def load_trusted_dit_model(
    checkpoint_path: str,
    *,
    model_id: str,
    attn_implementation: str,
    dtype: Any,
    importer: Callable[[str], Any] = importlib.import_module,
) -> Any:
    """Load DiT tensors using fixed application modules and safetensors only."""

    contract = inspect_dit_checkpoint(checkpoint_path, model_id=model_id)
    package = f"acestep.models.{contract.variant}"
    config_module = importer(f"{package}.configuration_acestep_v15")
    model_module = importer(
        f"{package}.{_VARIANT_MODEL_FILES[contract.variant]}"
    )
    config_class = getattr(config_module, _CONFIG_CLASS)
    model_class = getattr(model_module, _MODEL_CLASS)

    config = config_class.from_pretrained(
        contract.checkpoint_path,
        local_files_only=True,
    )
    return model_class.from_pretrained(
        contract.checkpoint_path,
        config=config,
        local_files_only=True,
        use_safetensors=True,
        attn_implementation=attn_implementation,
        dtype=dtype,
    )


def load_trusted_causal_lm(
    checkpoint_path: str,
    *,
    auto_model_class: Optional[Any] = None,
) -> Any:
    """Load a standard causal LM locally with custom code and pickle fallback off."""

    inspect_causal_lm_checkpoint(checkpoint_path)
    if auto_model_class is None:
        from transformers import AutoModelForCausalLM

        auto_model_class = AutoModelForCausalLM
    return auto_model_class.from_pretrained(
        checkpoint_path,
        trust_remote_code=False,
        local_files_only=True,
        use_safetensors=True,
    )
