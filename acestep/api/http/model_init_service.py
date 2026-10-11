"""Blocking model initialization helpers for API model service routes."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from acestep.api.model_registry import (
    approved_dit_model_ids,
    approved_lm_model_ids,
    normalize_model_identifier,
)
from acestep.gpu_config import (
    VRAM_AUTO_OFFLOAD_THRESHOLD_GB,
    get_gpu_config,
    resolve_lm_backend,
)


def _resolve_slot(
    app_state: Any,
    slot: Optional[int],
    get_model_name: Callable[[str], str],
) -> tuple:
    """Return ``(handler, config_attr, init_attr, error_attr, current_config_path)`` for *slot*.

    Raises ``RuntimeError`` when the requested slot's handler was never
    constructed (environment variable not set at startup).
    """

    slot = slot or 1
    if slot == 1:
        return (
            app_state.handler,
            "_config_path",
            "_initialized",
            "_init_error",
            getattr(app_state, "_config_path", ""),
        )

    handler_attr = f"handler{slot}"
    handler = getattr(app_state, handler_attr, None)
    if handler is None:
        env_var = f"ACESTEP_CONFIG_PATH{slot}"
        raise RuntimeError(
            f"Slot {slot} is not available because {env_var} was not set at "
            f"startup. Restart the API with {env_var} to enable this slot."
        )

    suffix = str(slot)
    return (
        handler,
        f"_config_path{suffix}",
        f"_initialized{suffix}",
        f"_init_error{suffix}",
        getattr(app_state, f"_config_path{suffix}", ""),
    )


def _registered_name(
    raw_value: Optional[str],
    *,
    fallback_value: str,
    get_model_name: Callable[[str], str],
    allowed_ids,
    field_name: str,
) -> str:
    explicit = str(raw_value or "").strip()
    if explicit:
        # Caller-supplied API values are validated exactly as received. Do not
        # basename an absolute/traversing path into an apparently valid model ID.
        identifier = explicit
    else:
        selected = str(fallback_value or "").strip()
        if not selected:
            raise RuntimeError(f"No {field_name} specified")
        # Existing startup state may retain an absolute path from an older build.
        # A fallback may reuse only its final registered identifier.
        identifier = get_model_name(selected) or selected
    return normalize_model_identifier(
        identifier,
        allowed_ids=allowed_ids,
        field_name=field_name,
    )


def initialize_models_for_request(
    app_state: Any,
    model_name: Optional[str],
    init_llm: bool,
    requested_lm_model_path: Optional[str],
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
    slot: Optional[int] = None,
) -> Dict[str, Optional[str]]:
    """Initialize API-selected DiT/LM models from registered identifiers only."""

    resolved_slot = slot or 1
    handler, config_attr, init_attr, error_attr, current_config = _resolve_slot(
        app_state, resolved_slot, get_model_name,
    )

    llm = app_state.llm_handler
    project_root = get_project_root()
    checkpoint_dir = os.path.join(project_root, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)

    target_model = _registered_name(
        model_name,
        fallback_value=get_model_name(current_config),
        get_model_name=get_model_name,
        allowed_ids=approved_dit_model_ids(),
        field_name="DiT model",
    )

    gpu_config = get_gpu_config()
    auto_offload = (
        gpu_config.gpu_memory_gb > 0
        and gpu_config.gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB
    )
    offload_to_cpu_env = os.getenv("ACESTEP_OFFLOAD_TO_CPU")
    offload_to_cpu = (
        env_bool("ACESTEP_OFFLOAD_TO_CPU", False)
        if offload_to_cpu_env is not None
        else auto_offload
    )
    use_flash_attention = env_bool("ACESTEP_USE_FLASH_ATTENTION", True)
    offload_dit_to_cpu = env_bool("ACESTEP_OFFLOAD_DIT_TO_CPU", False)
    compile_model = env_bool("ACESTEP_COMPILE_MODEL", False)
    device = os.getenv("ACESTEP_DEVICE", "auto")

    ensure_model_downloaded(target_model, checkpoint_dir)
    ensure_model_downloaded("vae", checkpoint_dir)

    status_msg, ok = handler.initialize_service(
        project_root=project_root,
        config_path=target_model,
        device=device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=offload_to_cpu,
        offload_dit_to_cpu=offload_dit_to_cpu,
    )
    if not ok:
        setattr(app_state, error_attr, status_msg)
        raise RuntimeError(f"DiT init failed for slot {resolved_slot}: {status_msg}")

    setattr(app_state, config_attr, target_model)
    setattr(app_state, init_attr, True)
    setattr(app_state, error_attr, None)

    loaded_lm_model: Optional[str] = None
    if init_llm:
        lm_model_id = _registered_name(
            requested_lm_model_path,
            fallback_value=os.getenv(
                "ACESTEP_LM_MODEL_PATH",
                "acestep-5Hz-lm-0.6B",
            ),
            get_model_name=get_model_name,
            allowed_ids=approved_lm_model_ids(),
            field_name="LM model",
        )

        # Publish only the normalized identifier after validation. Invalid
        # caller input cannot poison later lazy-load or restore state.
        os.environ["ACESTEP_INIT_LLM"] = "true"
        os.environ["ACESTEP_LM_MODEL_PATH"] = lm_model_id

        lm_backend = resolve_lm_backend(os.getenv("ACESTEP_LM_BACKEND"), gpu_config)
        lm_device = os.getenv("ACESTEP_LM_DEVICE", device)
        lm_offload_env = os.getenv("ACESTEP_LM_OFFLOAD_TO_CPU")
        lm_offload = (
            env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
            if lm_offload_env is not None
            else offload_to_cpu
        )

        ensure_model_downloaded(lm_model_id, checkpoint_dir)

        with app_state._llm_init_lock:
            llm_status, llm_ok = llm.initialize(
                checkpoint_dir=checkpoint_dir,
                lm_model_path=lm_model_id,
                backend=lm_backend,
                device=lm_device,
                offload_to_cpu=lm_offload,
                dtype=None,
            )
            if not llm_ok:
                app_state._llm_initialized = False
                app_state._llm_init_error = llm_status
                raise RuntimeError(f"LLM init failed: {llm_status}")
            app_state._llm_initialized = True
            app_state._llm_init_error = None
            app_state._llm_lazy_load_disabled = False
        loaded_lm_model = lm_model_id

    return {
        "slot": resolved_slot,
        "loaded_model": target_model,
        "loaded_lm_model": loaded_lm_model,
    }
