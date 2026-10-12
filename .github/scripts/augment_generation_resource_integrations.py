from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, content: str) -> None:
    (ROOT / rel).write_text(content, encoding="utf-8")


def replace_once(rel: str, old: str, new: str) -> None:
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:140]!r}")
    write(rel, text.replace(old, new, 1))


# Preserve compatibility with focused worker-loop fixtures that intentionally use
# a minimal store while still honoring cancellation on the production store.
replace_once(
    "acestep/api/jobs/worker_loops.py",
    "        reason = store.cancellation_reason(job_id)\n",
    "        cancellation_checker = getattr(store, \"cancellation_reason\", None)\n"
    "        reason = cancellation_checker(job_id) if callable(cancellation_checker) else None\n",
)

policy_path = ROOT / "acestep/api/generation_resource_policy.py"
policy = policy_path.read_text(encoding="utf-8")
marker = "# --- raw-body and extended generation boundary ---"
if marker in policy:
    raise RuntimeError("generation resource policy augmentation already present")
policy += r'''

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

        limit = self.path_limits.get(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = {}
        for key, value in scope.get("headers", []):
            headers[key.lower()] = value
        declared_raw = headers.get(b"content-length")
        if declared_raw is not None:
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
'''
policy_path.write_text(policy, encoding="utf-8")

replace_once(
    "acestep/api/route_setup.py",
    "from acestep.api.http.audio_route import register_audio_route\n",
    "from acestep.api.generation_resource_policy import (\n"
    "    RequestBodyLimitMiddleware,\n"
    "    default_generation_path_limits,\n"
    ")\n"
    "from acestep.api.http.audio_route import register_audio_route\n",
)
replace_once(
    "acestep/api/route_setup.py",
    "    app.add_middleware(\n        CORSMiddleware,\n",
    "    app.add_middleware(\n"
    "        RequestBodyLimitMiddleware,\n"
    "        path_limits=default_generation_path_limits(),\n"
    "    )\n\n"
    "    app.add_middleware(\n        CORSMiddleware,\n",
)

replace_once(
    "acestep/api/http/release_task_route.py",
    "from acestep.api.http.release_task_request_parser import parse_release_task_request\n",
    "from acestep.api.generation_resource_policy import (\n"
    "    GenerationLimitError,\n"
    "    generation_timeout_seconds,\n"
    "    validate_generate_request,\n"
    ")\n"
    "from acestep.api.http.release_task_request_parser import parse_release_task_request\n",
)
replace_once(
    "acestep/api/http/release_task_route.py",
    "        record = store.create()\n",
    "        try:\n"
    "            validate_generate_request(\n"
    "                req, lm_initialized=bool(getattr(app.state, \"_llm_initialized\", False))\n"
    "            )\n"
    "        except GenerationLimitError as exc:\n"
    "            for temp_path in temp_files:\n"
    "                try:\n"
    "                    os.remove(temp_path)\n"
    "                except OSError:\n"
    "                    pass\n"
    "            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n\n"
    "        record = store.create()\n"
    "        set_deadline = getattr(store, \"set_deadline\", None)\n"
    "        if callable(set_deadline):\n"
    "            set_deadline(record.job_id, generation_timeout_seconds())\n",
)

print("raw-body middleware, release-task validation, and queue compatibility integrated")
