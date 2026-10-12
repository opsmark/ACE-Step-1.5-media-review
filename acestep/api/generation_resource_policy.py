"""Central resource policy for network-reachable generation requests.

The policy is intentionally independent of any reverse proxy.  It bounds the
request before JSON/form parsing, validates text/base64 budgets before temporary
files or model work, and applies an absolute ceiling in addition to the current
hardware-aware GPU limits.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


_MIB = 1024 * 1024
_ASCII_WS_RE = re.compile(r"[\t\n\r\f\v ]+")


def _bounded_env_int(
    name: str,
    default: int,
    *,
    hard_min: int,
    hard_max: int,
) -> int:
    """Read an integer override that may tighten, but never defeat, a hard cap."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(hard_min, min(value, hard_max))


@dataclass(frozen=True)
class GenerationResourceLimits:
    max_request_body_bytes: int = _bounded_env_int(
        "ACESTEP_MAX_GENERATION_BODY_BYTES",
        64 * _MIB,
        hard_min=64 * 1024,
        hard_max=64 * _MIB,
    )
    max_audio_part_bytes: int = _bounded_env_int(
        "ACESTEP_MAX_AUDIO_PART_BYTES",
        32 * _MIB,
        hard_min=64 * 1024,
        hard_max=32 * _MIB,
    )
    max_total_audio_bytes: int = _bounded_env_int(
        "ACESTEP_MAX_TOTAL_AUDIO_BYTES",
        45 * _MIB,
        hard_min=64 * 1024,
        hard_max=45 * _MIB,
    )
    max_audio_parts: int = 2
    max_messages: int = 32
    max_content_parts: int = 8
    max_message_text_chars: int = 32_768
    max_total_message_text_chars: int = 96_000
    max_prompt_chars: int = 32_768
    max_lyrics_chars: int = 65_536
    max_sample_query_chars: int = 16_384
    max_audio_codes_chars: int = 2_000_000
    max_model_id_chars: int = 128
    max_batch_size: int = 8
    max_inference_steps: int = 200
    max_duration_seconds: float = 600.0
    max_seed_values: int = 8
    max_task_ids_per_query: int = 100
    max_param_fields: int = 128
    max_top_k: int = 1_000
    max_tokens: int = 4_096

    @property
    def max_audio_part_base64_chars(self) -> int:
        return math.ceil(self.max_audio_part_bytes / 3) * 4 + 128


LIMITS = GenerationResourceLimits()
SUPPORTED_AUDIO_FORMATS = frozenset(
    {"mp3", "wav", "wav32", "flac", "ogg", "opus", "m4a", "aac"}
)
SUPPORTED_TASK_TYPES = frozenset(
    {"text2music", "cover", "cover-nofsq", "repaint", "extract", "lego", "complete"}
)
SUPPORTED_INFER_METHODS = frozenset({"ode", "sde"})


class GenerationLimitError(ValueError):
    """A request exceeded a declared generation boundary."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def generation_timeout_seconds() -> int:
    """Return a bounded wall-clock deadline for every response mode."""
    return _bounded_env_int(
        "ACESTEP_GENERATION_TIMEOUT",
        600,
        hard_min=30,
        hard_max=3600,
    )


async def read_request_body_limited(request: Any, *, limit: Optional[int] = None) -> bytes:
    """Read an ASGI request body while enforcing the limit during streaming."""
    maximum = int(limit or LIMITS.max_request_body_bytes)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise GenerationLimitError("Invalid Content-Length header", status_code=400) from exc
        if declared < 0 or declared > maximum:
            raise GenerationLimitError(
                f"Generation request body exceeds {maximum} bytes",
                status_code=413,
            )

    body = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        if len(body) + len(chunk) > maximum:
            raise GenerationLimitError(
                f"Generation request body exceeds {maximum} bytes",
                status_code=413,
            )
        body.extend(chunk)
    return bytes(body)


async def read_json_object_limited(request: Any) -> dict[str, Any]:
    raw = await read_request_body_limited(request)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationLimitError("Request body must be valid UTF-8 JSON", status_code=400) from exc
    if not isinstance(value, dict):
        raise GenerationLimitError("Request JSON must be an object", status_code=400)
    return value


async def read_mapping_payload_limited(request: Any) -> dict[str, Any]:
    """Read bounded JSON, urlencoded, or multipart form data.

    The custom Gradio API historically accepted both JSON and form bodies.  A
    cloned Request parses the already-bounded bytes so chunked multipart bodies
    cannot bypass the byte ceiling.
    """
    raw = await read_request_body_limited(request)
    content_type = (request.headers.get("content-type") or "").lower()
    if "json" in content_type:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationLimitError("Request body must be valid UTF-8 JSON", status_code=400) from exc
        if not isinstance(value, dict):
            raise GenerationLimitError("Request JSON must be an object", status_code=400)
        return value

    from starlette.requests import Request as StarletteRequest

    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": raw, "more_body": False}

    cloned = StarletteRequest(request.scope, receive)
    try:
        form = await cloned.form()
    except Exception as exc:
        raise GenerationLimitError("Request form could not be parsed", status_code=400) from exc

    result: dict[str, Any] = {}
    try:
        items = form.multi_items()
    except AttributeError:
        items = form.items()
    for key, value in items:
        if hasattr(value, "filename"):
            close = getattr(value, "close", None)
            if close is not None:
                maybe_awaitable = close()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable
            raise GenerationLimitError(
                "File uploads are not accepted by this generation endpoint",
                status_code=415,
            )
        result[str(key)] = value
    return result


def _require_text(value: Any, *, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GenerationLimitError(f"{field} must be a string")
    if len(value) > maximum:
        raise GenerationLimitError(f"{field} exceeds {maximum} characters", status_code=413)
    return value


def validate_text_inputs(
    *,
    prompt: Any = "",
    global_caption: Any = "",
    lyrics: Any = "",
    sample_query: Any = "",
    audio_codes: Any = "",
    limits: GenerationResourceLimits = LIMITS,
) -> None:
    _require_text(prompt, field="prompt", maximum=limits.max_prompt_chars)
    _require_text(global_caption, field="global_caption", maximum=limits.max_prompt_chars)
    _require_text(lyrics, field="lyrics", maximum=limits.max_lyrics_chars)
    _require_text(sample_query, field="sample_query", maximum=limits.max_sample_query_chars)
    _require_text(audio_codes, field="audio_codes", maximum=limits.max_audio_codes_chars)


def _coerce_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise GenerationLimitError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GenerationLimitError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise GenerationLimitError(f"{field} must be finite")
    return number


def _coerce_int(value: Any, *, field: str) -> int:
    number = _coerce_float(value, field=field)
    if not number.is_integer():
        raise GenerationLimitError(f"{field} must be an integer")
    return int(number)


def effective_work_limits(
    *,
    lm_initialized: bool,
    gpu_config: Any = None,
    limits: GenerationResourceLimits = LIMITS,
) -> tuple[float, int]:
    """Intersect absolute ceilings with the active hardware policy."""
    config = gpu_config
    if config is None:
        try:
            from acestep.gpu_config import get_global_gpu_config

            config = get_global_gpu_config()
        except Exception:
            config = None
    if config is None:
        return limits.max_duration_seconds, limits.max_batch_size

    duration_attr = "max_duration_with_lm" if lm_initialized else "max_duration_without_lm"
    batch_attr = "max_batch_size_with_lm" if lm_initialized else "max_batch_size_without_lm"
    try:
        duration = min(limits.max_duration_seconds, float(getattr(config, duration_attr)))
        batch = min(limits.max_batch_size, int(getattr(config, batch_attr)))
    except (TypeError, ValueError, AttributeError):
        return limits.max_duration_seconds, limits.max_batch_size
    return max(0.1, duration), max(1, batch)


def validate_generation_work(
    *,
    duration: Any = None,
    batch_size: Any = None,
    inference_steps: Any = 8,
    task_type: Any = "text2music",
    infer_method: Any = "ode",
    audio_format: Any = "mp3",
    seed: Any = None,
    lm_initialized: bool = False,
    gpu_config: Any = None,
    limits: GenerationResourceLimits = LIMITS,
) -> tuple[float, int]:
    max_duration, max_batch = effective_work_limits(
        lm_initialized=lm_initialized,
        gpu_config=gpu_config,
        limits=limits,
    )

    if duration not in (None, "", -1, "-1"):
        duration_value = _coerce_float(duration, field="duration")
        if duration_value <= 0 or duration_value > max_duration:
            raise GenerationLimitError(
                f"duration must be greater than 0 and no more than {max_duration:g} seconds"
            )

    if batch_size not in (None, ""):
        batch_value = _coerce_int(batch_size, field="batch_size")
        if batch_value < 1 or batch_value > max_batch:
            raise GenerationLimitError(f"batch_size must be between 1 and {max_batch}")

    step_value = _coerce_int(inference_steps, field="inference_steps")
    if step_value < 1 or step_value > limits.max_inference_steps:
        raise GenerationLimitError(
            f"inference_steps must be between 1 and {limits.max_inference_steps}"
        )

    if not isinstance(task_type, str) or task_type not in SUPPORTED_TASK_TYPES:
        raise GenerationLimitError(f"Unsupported task_type: {task_type!r}")
    if not isinstance(infer_method, str) or infer_method not in SUPPORTED_INFER_METHODS:
        raise GenerationLimitError(f"Unsupported infer_method: {infer_method!r}")
    if not isinstance(audio_format, str) or audio_format.lower() not in SUPPORTED_AUDIO_FORMATS:
        raise GenerationLimitError(f"Unsupported audio format: {audio_format!r}")

    if isinstance(seed, str):
        seed_parts = [part.strip() for part in seed.split(",") if part.strip()]
        if len(seed_parts) > limits.max_seed_values:
            raise GenerationLimitError(
                f"seed contains more than {limits.max_seed_values} values"
            )
        for part in seed_parts:
            _coerce_int(part, field="seed")
    elif seed is not None:
        _coerce_int(seed, field="seed")

    return max_duration, max_batch


def _part_value(part: Any, field: str, default: Any = None) -> Any:
    if isinstance(part, Mapping):
        return part.get(field, default)
    return getattr(part, field, default)


def _normalized_base64_payload(data: str) -> str:
    if data.startswith("data:"):
        if "," not in data:
            raise GenerationLimitError("Malformed audio data URL", status_code=400)
        data = data.split(",", 1)[1]
    return _ASCII_WS_RE.sub("", data)


def estimate_decoded_base64_bytes(data: str) -> int:
    normalized = _normalized_base64_payload(data)
    if not normalized:
        return 0
    return (len(normalized) * 3) // 4


def validate_openrouter_request(
    request_model: Any,
    *,
    lm_initialized: bool,
    gpu_config: Any = None,
    limits: GenerationResourceLimits = LIMITS,
) -> None:
    model_id = _require_text(
        getattr(request_model, "model", ""),
        field="model",
        maximum=limits.max_model_id_chars,
    )
    if not model_id.strip():
        raise GenerationLimitError("model must not be empty")

    messages = getattr(request_model, "messages", None)
    if not isinstance(messages, list) or not (1 <= len(messages) <= limits.max_messages):
        raise GenerationLimitError(f"messages must contain 1 to {limits.max_messages} items")

    total_text = 0
    audio_parts = 0
    estimated_audio_bytes = 0
    for message in messages:
        name = getattr(message, "name", None)
        if name is not None:
            _require_text(name, field="message.name", maximum=128)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            text = _require_text(
                content,
                field="message.content",
                maximum=limits.max_message_text_chars,
            )
            total_text += len(text)
            continue
        if not isinstance(content, list) or len(content) > limits.max_content_parts:
            raise GenerationLimitError(
                f"message content must have at most {limits.max_content_parts} parts"
            )
        for part in content:
            part_type = _part_value(part, "type", "")
            if part_type == "text":
                text = _require_text(
                    _part_value(part, "text", ""),
                    field="message.text",
                    maximum=limits.max_message_text_chars,
                )
                total_text += len(text)
            elif part_type == "input_audio":
                audio_parts += 1
                audio_input = _part_value(part, "input_audio", None)
                if audio_input is None:
                    raise GenerationLimitError("input_audio content is missing")
                data = _require_text(
                    _part_value(audio_input, "data", ""),
                    field="input_audio.data",
                    maximum=limits.max_audio_part_base64_chars,
                )
                fmt = _part_value(audio_input, "format", "mp3")
                if not isinstance(fmt, str) or fmt.lower() not in SUPPORTED_AUDIO_FORMATS:
                    raise GenerationLimitError(f"Unsupported input audio format: {fmt!r}")
                estimate = estimate_decoded_base64_bytes(data)
                if estimate > limits.max_audio_part_bytes:
                    raise GenerationLimitError("An input audio part exceeds the decoded byte budget", status_code=413)
                estimated_audio_bytes += estimate
            else:
                raise GenerationLimitError(f"Unsupported message content type: {part_type!r}")

    if total_text > limits.max_total_message_text_chars:
        raise GenerationLimitError(
            f"Combined message text exceeds {limits.max_total_message_text_chars} characters",
            status_code=413,
        )
    if audio_parts > limits.max_audio_parts:
        raise GenerationLimitError(f"At most {limits.max_audio_parts} input audio parts are accepted")
    if estimated_audio_bytes > limits.max_total_audio_bytes:
        raise GenerationLimitError("Combined input audio exceeds the decoded byte budget", status_code=413)

    validate_text_inputs(
        prompt="",
        lyrics=getattr(request_model, "lyrics", ""),
        audio_codes=getattr(request_model, "audio_codes", ""),
        limits=limits,
    )
    audio_config = getattr(request_model, "audio_config", None)
    duration = getattr(audio_config, "duration", None) if audio_config is not None else None
    audio_format = getattr(audio_config, "format", "mp3") if audio_config is not None else "mp3"
    validate_generation_work(
        duration=duration,
        batch_size=getattr(request_model, "batch_size", None),
        inference_steps=getattr(request_model, "inference_steps", 8),
        task_type=getattr(request_model, "task_type", "text2music"),
        infer_method=getattr(request_model, "infer_method", "ode"),
        audio_format=audio_format,
        seed=getattr(request_model, "seed", None),
        lm_initialized=lm_initialized,
        gpu_config=gpu_config,
        limits=limits,
    )

    max_tokens = getattr(request_model, "max_tokens", None)
    if max_tokens is not None and not (1 <= int(max_tokens) <= limits.max_tokens):
        raise GenerationLimitError(f"max_tokens must be between 1 and {limits.max_tokens}")
    top_k = getattr(request_model, "top_k", None)
    if top_k is not None and not (0 <= int(top_k) <= limits.max_top_k):
        raise GenerationLimitError(f"top_k must be between 0 and {limits.max_top_k}")


def decode_audio_base64(
    data: str,
    audio_format: str,
    *,
    limits: GenerationResourceLimits = LIMITS,
) -> bytes:
    if not isinstance(audio_format, str) or audio_format.lower() not in SUPPORTED_AUDIO_FORMATS:
        raise GenerationLimitError(f"Unsupported input audio format: {audio_format!r}")
    text = _require_text(
        data,
        field="input_audio.data",
        maximum=limits.max_audio_part_base64_chars,
    )
    normalized = _normalized_base64_payload(text)
    if estimate_decoded_base64_bytes(text) > limits.max_audio_part_bytes:
        raise GenerationLimitError("Input audio exceeds the decoded byte budget", status_code=413)
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GenerationLimitError("Input audio is not valid base64", status_code=400) from exc
    if not decoded:
        raise GenerationLimitError("Input audio is empty", status_code=400)
    if len(decoded) > limits.max_audio_part_bytes:
        raise GenerationLimitError("Input audio exceeds the decoded byte budget", status_code=413)
    return decoded


def validate_task_id_query(task_ids: Any, *, limits: GenerationResourceLimits = LIMITS) -> list[str]:
    if not isinstance(task_ids, list):
        raise GenerationLimitError("task_id_list must be a JSON array")
    if len(task_ids) > limits.max_task_ids_per_query:
        raise GenerationLimitError(
            f"task_id_list may contain at most {limits.max_task_ids_per_query} items"
        )
    result: list[str] = []
    for task_id in task_ids:
        if not isinstance(task_id, str) or not (1 <= len(task_id) <= 128):
            raise GenerationLimitError("Each task_id must be a non-empty string of at most 128 characters")
        result.append(task_id)
    return result


def validate_param_object(value: Any, *, limits: GenerationResourceLimits = LIMITS) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GenerationLimitError("param_obj must be a JSON object")
    if len(value) > limits.max_param_fields:
        raise GenerationLimitError(f"param_obj may contain at most {limits.max_param_fields} fields")
    return value


# --- raw-body and extended generation boundary ---
_MAX_TIMESTEPS_CHARS = 16_384
_MAX_TRACK_CLASSES = 64
_MAX_TRACK_CLASS_CHARS = 256
_MAX_INSTRUCTION_CHARS = 32_768
_MAX_SMALL_TEXT_CHARS = 1_024


class RequestBodyTooLarge(Exception):
    """Internal signal raised before an oversized request reaches a route parser."""


class RequestBodyLimitMiddleware:
    """Pure ASGI middleware that bounds declared and chunked request bodies.

    Path-specific limits are enforced before FastAPI/Pydantic materializes the
    payload.  The endpoint validators remain defense in depth for callers that
    invoke handlers or parsing helpers without the assembled application.
    """

    def __init__(self, app: Any, *, path_limits: Optional[Mapping[str, int]] = None) -> None:
        self.app = app
        self.path_limits = {
            str(path): min(max(1, int(limit)), LIMITS.max_request_body_bytes)
            for path, limit in dict(path_limits or {}).items()
        }

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method", "").upper() not in {
            "POST", "PUT", "PATCH"
        }:
            await self.app(scope, receive, send)
            return

        request_path = str(scope.get("path", ""))
        normalized_path = request_path.rstrip("/") or "/"
        limit = self.path_limits.get(request_path)
        if limit is None:
            limit = self.path_limits.get(normalized_path)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared_values = [
            value for key, value in scope.get("headers", [])
            if key.lower() == b"content-length"
        ]
        if declared_values:
            if len(set(declared_values)) != 1:
                await self._reject(
                    scope, receive, send, 400, "Conflicting Content-Length headers"
                )
                return
            declared_raw = declared_values[0]
            try:
                declared = int(declared_raw)
            except (TypeError, ValueError):
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared > limit:
                await self._reject(
                    scope, receive, send, 413,
                    f"Generation request body exceeds {limit} bytes",
                )
                return

        observed = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal observed
            message = await receive()
            if message.get("type") == "http.request":
                observed += len(message.get("body", b""))
                if observed > limit:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(
                scope, receive, send, 413,
                f"Generation request body exceeds {limit} bytes",
            )

    @staticmethod
    async def _reject(
        scope: dict[str, Any], receive: Any, send: Any, status: int, detail: str
    ) -> None:
        from starlette.responses import JSONResponse

        await JSONResponse(
            status_code=status,
            content={"detail": detail},
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )(scope, receive, send)


def default_generation_path_limits() -> dict[str, int]:
    """Return byte ceilings for every network-reachable generation body."""
    limit = LIMITS.max_request_body_bytes
    return {
        "/release_task": limit,
        "/v1/chat/completions": limit,
        "/query_result": min(limit, 1 * 1024 * 1024),
        "/create_random_sample": min(limit, 2 * 1024 * 1024),
        "/format_input": min(limit, 2 * 1024 * 1024),
        "/v1/create_sample": min(limit, 2 * 1024 * 1024),
    }


def validate_generate_request(
    request_model: Any,
    *,
    lm_initialized: bool,
    gpu_config: Any = None,
    limits: GenerationResourceLimits = LIMITS,
) -> tuple[float, int]:
    """Validate the decomposed `/release_task` request before queue admission."""
    validate_text_inputs(
        prompt=getattr(request_model, "prompt", ""),
        global_caption=getattr(request_model, "global_caption", ""),
        lyrics=getattr(request_model, "lyrics", ""),
        sample_query=getattr(request_model, "sample_query", ""),
        audio_codes=getattr(request_model, "audio_code_string", ""),
        limits=limits,
    )
    _require_text(
        getattr(request_model, "instruction", ""),
        field="instruction",
        maximum=_MAX_INSTRUCTION_CHARS,
    )
    _require_text(
        getattr(request_model, "lm_negative_prompt", ""),
        field="lm_negative_prompt",
        maximum=limits.max_prompt_chars,
    )
    for field in (
        "model", "lm_model_path", "key_scale", "time_signature", "vocal_language",
        "track_name", "dcw_wavelet",
    ):
        _require_text(
            getattr(request_model, field, ""),
            field=field,
            maximum=limits.max_model_id_chars if field in {"model", "lm_model_path"}
            else _MAX_SMALL_TEXT_CHARS,
        )

    timesteps = getattr(request_model, "timesteps", None)
    if timesteps is not None:
        _require_text(timesteps, field="timesteps", maximum=_MAX_TIMESTEPS_CHARS)

    track_classes = getattr(request_model, "track_classes", None)
    if track_classes is not None:
        if not isinstance(track_classes, list):
            raise GenerationLimitError("track_classes must be an array")
        if len(track_classes) > _MAX_TRACK_CLASSES:
            raise GenerationLimitError(
                f"track_classes may contain at most {_MAX_TRACK_CLASSES} items"
            )
        for index, item in enumerate(track_classes):
            _require_text(
                item,
                field=f"track_classes[{index}]",
                maximum=_MAX_TRACK_CLASS_CHARS,
            )

    return validate_generation_work(
        duration=getattr(request_model, "audio_duration", None),
        batch_size=getattr(request_model, "batch_size", None),
        inference_steps=getattr(request_model, "inference_steps", 8),
        task_type=getattr(request_model, "task_type", "text2music"),
        infer_method=getattr(request_model, "infer_method", "ode"),
        audio_format=getattr(request_model, "audio_format", "mp3"),
        seed=getattr(request_model, "seed", None),
        lm_initialized=lm_initialized,
        gpu_config=gpu_config,
        limits=limits,
    )
