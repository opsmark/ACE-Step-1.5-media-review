"""ACE-Step training public API with dependency-lazy exports.

Importing a lightweight submodule such as :mod:`acestep.training.path_safety`
should not initialize the dataset/audio/trainer stack. Public symbols remain
available from ``acestep.training`` and are imported only when accessed.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    # Dataset builder
    "DatasetBuilder": ("acestep.training.dataset_builder", "DatasetBuilder"),
    "AudioSample": ("acestep.training.dataset_builder", "AudioSample"),
    # Configs
    "LoRAConfig": ("acestep.training.configs", "LoRAConfig"),
    "LoKRConfig": ("acestep.training.configs", "LoKRConfig"),
    "TrainingConfig": ("acestep.training.configs", "TrainingConfig"),
    # LoRA injection
    "inject_lora_into_dit": (
        "acestep.training.lora_injection",
        "inject_lora_into_dit",
    ),
    "freeze_non_lora_parameters": (
        "acestep.training.lora_injection",
        "freeze_non_lora_parameters",
    ),
    # LoRA checkpoints
    "save_lora_weights": ("acestep.training.lora_checkpoint", "save_lora_weights"),
    "load_lora_weights": ("acestep.training.lora_checkpoint", "load_lora_weights"),
    "save_training_checkpoint": (
        "acestep.training.lora_checkpoint",
        "save_training_checkpoint",
    ),
    "load_training_checkpoint": (
        "acestep.training.lora_checkpoint",
        "load_training_checkpoint",
    ),
    # LoRA utilities
    "merge_lora_weights": ("acestep.training.lora_utils", "merge_lora_weights"),
    "check_peft_available": (
        "acestep.training.lora_utils",
        "check_peft_available",
    ),
    # LoKr utilities
    "inject_lokr_into_dit": (
        "acestep.training.lokr_utils",
        "inject_lokr_into_dit",
    ),
    "save_lokr_weights": ("acestep.training.lokr_utils", "save_lokr_weights"),
    "load_lokr_weights": ("acestep.training.lokr_utils", "load_lokr_weights"),
    "check_lycoris_available": (
        "acestep.training.lokr_utils",
        "check_lycoris_available",
    ),
    # Data modules
    "PreprocessedTensorDataset": (
        "acestep.training.data_module",
        "PreprocessedTensorDataset",
    ),
    "PreprocessedDataModule": (
        "acestep.training.data_module",
        "PreprocessedDataModule",
    ),
    "collate_preprocessed_batch": (
        "acestep.training.data_module",
        "collate_preprocessed_batch",
    ),
    "AceStepTrainingDataset": (
        "acestep.training.data_module",
        "AceStepTrainingDataset",
    ),
    "AceStepDataModule": ("acestep.training.data_module", "AceStepDataModule"),
    "collate_training_batch": (
        "acestep.training.data_module",
        "collate_training_batch",
    ),
    "load_dataset_from_json": (
        "acestep.training.data_module",
        "load_dataset_from_json",
    ),
    # Trainer
    "LoRATrainer": ("acestep.training.trainer", "LoRATrainer"),
    "LoKRTrainer": ("acestep.training.trainer", "LoKRTrainer"),
    "PreprocessedLoRAModule": (
        "acestep.training.trainer",
        "PreprocessedLoRAModule",
    ),
    "PreprocessedLoKRModule": (
        "acestep.training.trainer",
        "PreprocessedLoKRModule",
    ),
    "LIGHTNING_AVAILABLE": (
        "acestep.training.trainer",
        "LIGHTNING_AVAILABLE",
    ),
}


def __getattr__(name: str) -> Any:
    """Load one historical public export on first access and cache it."""

    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


def check_lightning_available() -> bool:
    """Check whether the trainer's Lightning dependency is available."""

    return bool(__getattr__("LIGHTNING_AVAILABLE"))


__all__ = [
    "DatasetBuilder",
    "AudioSample",
    "LoRAConfig",
    "LoKRConfig",
    "TrainingConfig",
    "inject_lora_into_dit",
    "freeze_non_lora_parameters",
    "save_lora_weights",
    "load_lora_weights",
    "save_training_checkpoint",
    "load_training_checkpoint",
    "merge_lora_weights",
    "check_peft_available",
    "inject_lokr_into_dit",
    "save_lokr_weights",
    "load_lokr_weights",
    "check_lycoris_available",
    "PreprocessedTensorDataset",
    "PreprocessedDataModule",
    "collate_preprocessed_batch",
    "AceStepTrainingDataset",
    "AceStepDataModule",
    "collate_training_batch",
    "load_dataset_from_json",
    "LoRATrainer",
    "LoKRTrainer",
    "PreprocessedLoRAModule",
    "PreprocessedLoKRModule",
    "check_lightning_available",
    "LIGHTNING_AVAILABLE",
]
