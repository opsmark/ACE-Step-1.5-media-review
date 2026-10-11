"""Training API route registration facade."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from loguru import logger

from acestep.api.train_api_dataset_service import register_training_dataset_routes
from acestep.api.train_api_lokr_start_route import register_lokr_training_start_route
from acestep.api.train_api_lora_start_route import register_lora_training_start_route
from acestep.api.train_api_models import ExportLoRARequest, initialize_training_state
from acestep.api.training_export_service import (
    TrainingExportConflict,
    TrainingExportError,
    TrainingExportNotFound,
    export_training_adapter,
)


def register_training_api_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    start_tensorboard: Callable[[FastAPI, str], Optional[str]],
    stop_tensorboard: Callable[[FastAPI], None],
    temporary_llm_model: Callable[[FastAPI, Any, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register all training-related endpoints onto ``app``."""

    register_lora_training_start_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        start_tensorboard=start_tensorboard,
    )
    register_lokr_training_start_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        start_tensorboard=start_tensorboard,
    )
    register_training_dataset_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        temporary_llm_model=temporary_llm_model,
        atomic_write_json=atomic_write_json,
        append_jsonl=append_jsonl,
    )

    @app.post("/v1/training/stop")
    async def stop_training(_: None = Depends(verify_api_key)):
        """Stop the current training process."""

        initialize_training_state(app)
        training_state = app.state.training_state
        if training_state.get("is_training", False):
            training_state["should_stop"] = True
        try:
            stop_tensorboard(app)
        except Exception:
            logger.exception("Failed to stop tensorboard process")

        training_state.update(
            {
                "current_step": 0,
                "current_loss": None,
                "status": "Stopping...",
                "loss_history": [],
                "training_log": "",
                "tensorboard_url": None,
                "tensorboard_logdir": None,
                "steps_per_second": 0.0,
                "estimated_time_remaining": 0.0,
                "error": None,
            }
        )
        if training_state.get("is_training", False):
            return wrap_response({"message": "Stopping training..."})
        return wrap_response({"message": "No training in progress"})

    @app.get("/v1/training/status")
    async def get_training_status(_: None = Depends(verify_api_key)):
        """Get current training status."""

        initialize_training_state(app)
        ts = app.state.training_state
        payload: Dict[str, Any] = {
            "is_training": ts.get("is_training", False),
            "should_stop": ts.get("should_stop", False),
            "current_step": ts.get("current_step", 0),
            "current_loss": ts.get("current_loss"),
            "status": ts.get("status", "Idle"),
            "config": ts.get("config", {}),
            "tensor_dir": ts.get("tensor_dir", ""),
            "loss_history": ts.get("loss_history", []),
            "tensorboard_url": ts.get("tensorboard_url"),
            "tensorboard_logdir": ts.get("tensorboard_logdir"),
            "training_log": ts.get("training_log", ""),
            "start_time": ts.get("start_time"),
            "current_epoch": ts.get("current_epoch", 0),
            "steps_per_second": ts.get("steps_per_second", 0.0),
            "estimated_time_remaining": ts.get("estimated_time_remaining", 0.0),
            "error": ts.get("error"),
        }
        return wrap_response(payload)

    @app.post("/v1/training/load_tensor_info")
    async def load_tensor_info(request: dict, _: None = Depends(verify_api_key)):
        """Load preprocessed tensor dataset info from directory."""

        tensor_dir = str(request.get("tensor_dir", "")).strip()
        if not tensor_dir:
            raise HTTPException(status_code=400, detail="Please enter a tensor directory path")
        if not os.path.exists(tensor_dir):
            raise HTTPException(status_code=400, detail=f"Directory not found: {tensor_dir}")
        if not os.path.isdir(tensor_dir):
            raise HTTPException(status_code=400, detail=f"Not a directory: {tensor_dir}")

        manifest_path = os.path.join(tensor_dir, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                metadata = manifest.get("metadata", {}) or {}
                num_samples = int(manifest.get("num_samples", 0))
                dataset_name = metadata.get("name", "Unknown")
                custom_tag = metadata.get("custom_tag", "")
                message = f"✅ Loaded preprocessed dataset: {dataset_name}\n📊 Samples: {num_samples} preprocessed tensors"
                if custom_tag:
                    message += f"\n🏷️ Custom Tag: {custom_tag}"
                return wrap_response(
                    {
                        "dataset_name": dataset_name,
                        "num_samples": num_samples,
                        "custom_tag": custom_tag,
                        "tensor_dir": tensor_dir,
                        "message": message,
                    }
                )
            except Exception:
                logger.exception("Failed to parse tensor manifest, fallback to .pt scan")

        pt_files = [f for f in os.listdir(tensor_dir) if f.endswith(".pt")]
        if not pt_files:
            raise HTTPException(status_code=400, detail=f"No .pt tensor files found in {tensor_dir}")
        return wrap_response(
            {
                "dataset_name": "Unknown",
                "num_samples": len(pt_files),
                "custom_tag": "",
                "tensor_dir": tensor_dir,
                "message": f"✅ Found {len(pt_files)} tensor files in {tensor_dir}\n⚠️ No manifest.json found - using all .pt files",
            }
        )

    @app.post("/v1/training/export")
    async def export_lora(request: ExportLoRARequest, _: None = Depends(verify_api_key)):
        """Export trained LoRA/LoKr weights to a new contained directory."""

        try:
            result = export_training_adapter(
                lora_output_dir=request.lora_output_dir,
                export_path=request.export_path,
            )
        except TrainingExportNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TrainingExportConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TrainingExportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Training export failed")
            return wrap_response(None, code=500, error=f"Export failed: {exc}")

        return wrap_response(
            {
                "message": "LoRA exported successfully",
                "export_path": result.export_path,
                "source": result.source_path,
            }
        )
