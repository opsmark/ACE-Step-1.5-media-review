"""Bound request memory and generation work before expensive processing."""

from __future__ import annotations

import base64
import binascii
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

# Absolute ceilings cannot be disabled through environment variables. Operators
# may reduce the active limits or raise defaults only up to these reviewed caps.
HARD_MAX_REQUEST_BYTES = 64 * 1024 * 1024
HARD_MAX_AUDIO_BYTES = 24 * 1024 * 1024
HARD_MAX_AUDIO_INPUTS = 2
HARD_MAX_MESSAGE_COUNT = 32
HARD_MAX_TEXT_CHARS = 64 * 1024
HARD_MAX_LYRICS_CHARS = 128 * 1024
HARD_MAX_AUDIO_CODES_CHARS = 4 * 1024 * 1024
HARD_MAX_INFERENCE_STEPS = 200
HARD_MAX_BATCH_SIZE = 8
HARD_MAX_DURATION_SECONDS = 600.0
HARD_MAX_STREAM_SECONDS = 3600
HARD_MAX_TIMESTEPS_CHARS = 16 * 1024
HARD_MAX_TRACK_CLASSES = 64
HARD_MAX_TRACK_CLASS_CHARS = 256

DEFAULT_REQUEST_BYTES = 32 * 1024 * 1024
DEFAULT_AUDIO_BYTES = 24 * 1024 * 1024
DEFAULT_STREAM_SECONDS = 900

_ALLOWED_AUDIO_FORMATS = frozenset(
    {"mp3", "wav", "wav32", "flac", "ogg", "opus", "aac", "m4a"}
)
_ALLOWED_TASK_TYPES = frozenset(
    {"text2music", "cover", "cover-nofsq", "repaint", "extract", "lego", "complete"}
)
_ALLOWED_INFER_METHODS = frozenset({"ode", "sde"})


class ResourceLimitError(ValueError):
    """Raised when a request exceeds an explicit resource budget."""


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ResourceLimitError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ResourceLimitError(
            f"{name} must be between {minimum} and {maximum}; received {value}"
        )
    return value


def request_byte_limit() -> int:
    return _bounded_env_int(
        "ACESTEP_MAX_REQUEST_BYTES",
        DEFAULT_REQUEST_BYTES,
        minimum=1024,
        maximum=HARD_MAX_REQUEST_BYTES,
    )


def decoded_audio_byte_limit() -> int:
    return _bounded_env_int(
        "ACESTEP_MAX_AUDIO_BYTES",
        DEFAULT_AUDIO_BYTES,
        minimum=1024,
        maximum=HARD_MAX_AUDIO_BYTES,
    )


def generation_timeout_seconds() -> int:
    return _bounded_env_int(
        "ACESTEP_GENERATION_TIMEOUT",
        DEFAULT_STREAM_SECONDS,
        minimum=1,
        maximum=HARD_MAX_STREAM_SECONDS,
    )


@dataclass(frozen=True)
class WorkBudget:
    duration_seconds: float
    batch_size: int
    inference_steps: int


def _gpu_work_caps(state: Any = None) -> tuple[float, int]:
    """Return hardware-aware duration/batch ceilings with safe fallback."""

    try:
        from acestep.gpu_config import get_global_gpu_config

        config = get_global_gpu_config()
        lm_active = bool(getattr(state, "_llm_initialized", False)) if state else False
        duration = (
            config.max_duration_with_lm
            if lm_active
            else config.max_duration_without_lm
        )
        batch = (
            config.max_batch_size_with_lm
            if lm_active
            else config.max_batch_size_without_lm
        )
        return (
            min(HARD_MAX_DURATION_SECONDS, max(0.1, float(duration))),
            min(HARD_MAX_BATCH_SIZE, max(1, int(batch))),
        )
    except Exception:
        # Fail closed enough for a CPU/unknown environment while retaining a
        # usable local generation path. This is not a substitute for detection.
        return min(HARD_MAX_DURATION_SECONDS, 300.0), 1


def work_budget_for_state(
    state: Any = None,
    *,
    duration_seconds: Optional[float],
    batch_size: Optional[int],
    inference_steps: Optional[int],
) -> WorkBudget:
    """Validate and normalize one request's expensive generation factors."""

    max_duration, max_batch = _gpu_work_caps(state)
    duration = 60.0 if duration_seconds is None else float(duration_seconds)
    batch = 1 if batch_size is None else int(batch_size)
    steps = 8 if inference_steps is None else int(inference_steps)

    if not math.isfinite(duration) or duration < 0.1 or duration > max_duration:
        raise ResourceLimitError(
            f"audio duration must be between 0.1 and {max_duration:g} seconds "
            "for the active hardware/model state"
        )
    if batch < 1 or batch > max_batch:
        raise ResourceLimitError(
            f"batch_size must be between 1 and {max_batch} for the active "
            "hardware/model state"
        )
    if steps < 1 or steps > HARD_MAX_INFERENCE_STEPS:
        raise ResourceLimitError(
            f"inference_steps must be between 1 and {HARD_MAX_INFERENCE_STEPS}"
        )
    return WorkBudget(duration, batch, steps)


def _require_text(name: str, value: Any, maximum: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > maximum:
        raise ResourceLimitError(
            f"{name} exceeds the {maximum}-character limit"
        )
    return text


def _normalize_audio_payload(value: str) -> str:
    payload = value.strip()
    if "," in payload and payload.lower().startswith("data:"):
        header, payload = payload.split(",", 1)
        if ";base64" not in header.lower():
            raise ResourceLimitError("audio data URL must use base64 encoding")
    if not payload:
        raise ResourceLimitError("audio payload is empty")
    if any(char.isspace() for char in payload):
        raise ResourceLimitError("audio base64 must not contain whitespace")
    return payload


def _estimated_decoded_size(payload: str) -> int:
    padding = 2 if payload.endswith("==") else 1 if payload.endswith("=") else 0
    return max(0, (len(payload) * 3) // 4 - padding)


def validate_audio_base64(value: str) -> None:
    """Reject oversized/obviously invalid base64 before allocating decoded bytes."""

    payload = _normalize_audio_payload(value)
    maximum = decoded_audio_byte_limit()
    encoded_ceiling = 4 * ((maximum + 2) // 3)
    if len(payload) > encoded_ceiling or _estimated_decoded_size(payload) > maximum:
        raise ResourceLimitError(
            f"decoded audio exceeds the {maximum}-byte limit"
        )


def decode_audio_base64(value: str) -> bytes:
    """Strictly decode one bounded base64 audio payload."""

    validate_audio_base64(value)
    payload = _normalize_audio_payload(value)
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ResourceLimitError("audio payload is not valid base64") from exc
    maximum = decoded_audio_byte_limit()
    if len(decoded) > maximum:
        raise ResourceLimitError(
            f"decoded audio exceeds the {maximum}-byte limit"
        )
    return decoded


def validate_openrouter_request(req: Any, state: Any = None) -> WorkBudget:
    """Validate text/audio counts and work factors before audio materialization."""

    messages = list(getattr(req, "messages", None) or [])
    if not messages or len(messages) > HARD_MAX_MESSAGE_COUNT:
        raise ResourceLimitError(
            f"messages must contain between 1 and {HARD_MAX_MESSAGE_COUNT} items"
        )

    total_text = 0
    audio_count = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total_text += len(content)
            continue
        if not isinstance(content, list):
            raise ResourceLimitError("message content must be text or a list")
        for part in content:
            part_type = part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
            if part_type == "text":
                text = part.get("text", "") if isinstance(part, dict) else getattr(part, "text", "")
                total_text += len(str(text or ""))
            elif part_type == "input_audio":
                audio_count += 1
                audio = part.get("input_audio", {}) if isinstance(part, dict) else getattr(part, "input_audio", None)
                data = audio.get("data", "") if isinstance(audio, dict) else getattr(audio, "data", "")
                fmt = audio.get("format", "mp3") if isinstance(audio, dict) else getattr(audio, "format", "mp3")
                if str(fmt).lower().lstrip(".") not in _ALLOWED_AUDIO_FORMATS:
                    raise ResourceLimitError(f"unsupported input audio format: {fmt!r}")
                validate_audio_base64(str(data or ""))
            else:
                raise ResourceLimitError(f"unsupported message content type: {part_type!r}")

    if total_text > HARD_MAX_TEXT_CHARS:
        raise ResourceLimitError(
            f"combined message text exceeds {HARD_MAX_TEXT_CHARS} characters"
        )
    if audio_count > HARD_MAX_AUDIO_INPUTS:
        raise ResourceLimitError(
            f"at most {HARD_MAX_AUDIO_INPUTS} input audio items are allowed"
        )

    _require_text("lyrics", getattr(req, "lyrics", ""), HARD_MAX_LYRICS_CHARS)
    _require_text(
        "audio_codes",
        getattr(req, "audio_codes", ""),
        HARD_MAX_AUDIO_CODES_CHARS,
    )
    model = _require_text("model", getattr(req, "model", ""), 256)
    if not model:
        raise ResourceLimitError("model is required")

    task_type = str(getattr(req, "task_type", "text2music") or "text2music")
    if task_type not in _ALLOWED_TASK_TYPES:
        raise ResourceLimitError(f"unsupported task_type: {task_type!r}")
    infer_method = str(getattr(req, "infer_method", "ode") or "ode")
    if infer_method not in _ALLOWED_INFER_METHODS:
        raise ResourceLimitError(f"unsupported infer_method: {infer_method!r}")

    audio_config = getattr(req, "audio_config", None)
    if audio_config is not None:
        fmt = str(getattr(audio_config, "format", "mp3") or "mp3").lower().lstrip(".")
        if fmt not in _ALLOWED_AUDIO_FORMATS:
            raise ResourceLimitError(f"unsupported output audio format: {fmt!r}")
        duration = getattr(audio_config, "duration", None)
    else:
        duration = None

    return work_budget_for_state(
        state,
        duration_seconds=duration,
        batch_size=getattr(req, "batch_size", None),
        inference_steps=getattr(req, "inference_steps", None),
    )


def validate_generate_request(req: Any, state: Any = None) -> WorkBudget:
    """Validate the decomposed `/release_task` request before queue admission."""

    for name, maximum in (
        ("prompt", HARD_MAX_TEXT_CHARS),
        ("global_caption", HARD_MAX_TEXT_CHARS),
        ("lyrics", HARD_MAX_LYRICS_CHARS),
        ("sample_query", HARD_MAX_TEXT_CHARS),
        ("instruction", HARD_MAX_TEXT_CHARS),
        ("audio_code_string", HARD_MAX_AUDIO_CODES_CHARS),
        ("lm_negative_prompt", HARD_MAX_TEXT_CHARS),
    ):
        _require_text(name, getattr(req, name, ""), maximum)

    timesteps = getattr(req, "timesteps", None)
    if timesteps is not None:
        _require_text("timesteps", timesteps, HARD_MAX_TIMESTEPS_CHARS)

    track_classes = getattr(req, "track_classes", None)
    if track_classes is not None:
        if len(track_classes) > HARD_MAX_TRACK_CLASSES:
            raise ResourceLimitError(
                f"track_classes exceeds {HARD_MAX_TRACK_CLASSES} items"
            )
        for index, item in enumerate(track_classes):
            _require_text(
                f"track_classes[{index}]",
                item,
                HARD_MAX_TRACK_CLASS_CHARS,
            )

    task_type = str(getattr(req, "task_type", "text2music") or "text2music")
    if task_type not in _ALLOWED_TASK_TYPES:
        raise ResourceLimitError(f"unsupported task_type: {task_type!r}")
    infer_method = str(getattr(req, "infer_method", "ode") or "ode")
    if infer_method not in _ALLOWED_INFER_METHODS:
        raise ResourceLimitError(f"unsupported infer_method: {infer_method!r}")
    fmt = str(getattr(req, "audio_format", "mp3") or "mp3").lower().lstrip(".")
    if fmt not in _ALLOWED_AUDIO_FORMATS:
        raise ResourceLimitError(f"unsupported output audio format: {fmt!r}")

    return work_budget_for_state(
        state,
        duration_seconds=getattr(req, "audio_duration", None),
        batch_size=getattr(req, "batch_size", None),
        inference_steps=getattr(req, "inference_steps", None),
    )


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """ASGI middleware that bounds declared and chunked request bodies."""

    def __init__(
        self,
        app: Any,
        *,
        path_limits: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.app = app
        self.path_limits = dict(path_limits or {})

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = self.path_limits.get(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return
        limit = min(int(limit), HARD_MAX_REQUEST_BYTES)

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > limit:
                    await JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body exceeds {limit} bytes"},
                    )(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )(scope, receive, send)
                return

        observed = 0

        async def limited_receive() -> dict:
            nonlocal observed
            message = await receive()
            if message.get("type") == "http.request":
                observed += len(message.get("body", b""))
                if observed > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {limit} bytes"},
            )(scope, receive, send)


def default_generation_path_limits() -> dict[str, int]:
    limit = request_byte_limit()
    return {
        "/release_task": limit,
        "/v1/chat/completions": limit,
        "/query_result": min(limit, 1024 * 1024),
        "/create_random_sample": min(limit, 2 * 1024 * 1024),
        "/format_input": min(limit, 2 * 1024 * 1024),
        "/v1/create_sample": min(limit, 2 * 1024 * 1024),
    }


async def read_bounded_json(request: Request) -> dict[str, Any]:
    """Read one JSON request with an explicit byte limit."""

    limit = request_byte_limit()
    chunks: list[bytes] = []
    observed = 0
    async for chunk in request.stream():
        observed += len(chunk)
        if observed > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Request body exceeds {limit} bytes",
            )
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return payload


async def read_bounded_json_or_form(request: Request) -> dict[str, Any]:
    """Read bounded JSON or URL-encoded form data without multipart decoding."""

    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    limit = request_byte_limit()
    chunks: list[bytes] = []
    observed = 0
    async for chunk in request.stream():
        observed += len(chunk)
        if observed > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Request body exceeds {limit} bytes",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)

    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
        if not isinstance(value, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        return value
    if content_type in {"application/x-www-form-urlencoded", ""}:
        try:
            return dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Form body must be UTF-8") from exc
    if content_type.startswith("multipart/"):
        raise HTTPException(
            status_code=415,
            detail="Multipart is not supported by this text-only endpoint",
        )
    raise HTTPException(status_code=415, detail=f"Unsupported Content-Type: {content_type}")
