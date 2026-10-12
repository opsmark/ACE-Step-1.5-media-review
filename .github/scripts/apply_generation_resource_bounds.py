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
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:120]!r}")
    write(rel, text.replace(old, new, 1))


def replace_all(rel: str, old: str, new: str, expected: int) -> None:
    text = read(rel)
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{rel}: expected {expected} targets, found {count}: {old[:120]!r}")
    write(rel, text.replace(old, new))


def replace_between(rel: str, start: str, end: str, replacement: str) -> None:
    text = read(rel)
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{rel}: start marker not found: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{rel}: end marker not found: {end!r}")
    write(rel, text[:start_index] + replacement + text[end_index:])


# ---------------------------------------------------------------------------
# Pydantic request boundaries
# ---------------------------------------------------------------------------
replace_once(
    "acestep/openrouter_models.py",
    "from pydantic import BaseModel, Field\n",
    "from pydantic import BaseModel, Field\n\nfrom acestep.api.generation_resource_policy import LIMITS\n",
)
replace_once(
    "acestep/openrouter_models.py",
    '    data: str = Field(..., description="Base64-encoded audio data")\n    format: str = Field(default="mp3", description="Audio format (mp3, wav, flac, etc.)")\n',
    '    data: str = Field(\n        ...,\n        max_length=LIMITS.max_audio_part_base64_chars,\n        description="Base64-encoded audio data",\n    )\n    format: str = Field(\n        default="mp3", max_length=8, description="Audio format (mp3, wav, flac, etc.)"\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    text: str = Field(..., description="Text content")\n',
    '    text: str = Field(\n        ..., max_length=LIMITS.max_message_text_chars, description="Text content"\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    "ContentPart = Union[TextContent, AudioContent, Dict[str, Any]]\n",
    "ContentPart = Union[TextContent, AudioContent]\n",
)
replace_once(
    "acestep/openrouter_models.py",
    '    duration: Optional[float] = Field(default=None, description="Target audio duration in seconds")\n',
    '    duration: Optional[float] = Field(\n        default=None, gt=0, le=LIMITS.max_duration_seconds,\n        description="Target audio duration in seconds",\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    model: str = Field(..., description="Model ID to use")\n    messages: List[ChatMessage] = Field(..., description="List of messages")\n',
    '    model: str = Field(\n        ..., min_length=1, max_length=LIMITS.max_model_id_chars, description="Model ID to use"\n    )\n    messages: List[ChatMessage] = Field(\n        ..., min_length=1, max_length=LIMITS.max_messages, description="List of messages"\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    top_k: Optional[int] = Field(default=None, ge=0)\n    max_tokens: Optional[int] = Field(default=None, ge=1)\n',
    '    top_k: Optional[int] = Field(default=None, ge=0, le=LIMITS.max_top_k)\n    max_tokens: Optional[int] = Field(default=None, ge=1, le=LIMITS.max_tokens)\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    guidance_scale: Optional[float] = Field(default=None, description="Classifier-free guidance scale")\n    batch_size: Optional[int] = Field(default=None, description="Number of audio samples to generate")\n',
    '    guidance_scale: Optional[float] = Field(\n        default=None, ge=0, le=50, description="Classifier-free guidance scale"\n    )\n    batch_size: Optional[int] = Field(\n        default=None, ge=1, le=LIMITS.max_batch_size,\n        description="Number of audio samples to generate",\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    lyrics: str = Field(default="", description="Direct lyrics input (bypass message parsing)")\n',
    '    lyrics: str = Field(\n        default="", max_length=LIMITS.max_lyrics_chars,\n        description="Direct lyrics input (bypass message parsing)",\n    )\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    task_type: str = Field(default="text2music", description="Task type: text2music, cover, cover-nofsq, repaint, extract, lego, complete")\n',
    '    task_type: Literal[\n        "text2music", "cover", "cover-nofsq", "repaint", "extract", "lego", "complete"\n    ] = Field(default="text2music", description="Generation task type")\n',
)
replace_once(
    "acestep/openrouter_models.py",
    '    audio_codes: str = Field(default="", description="Pre-computed audio codes (bypass auto-conversion)")\n    cover_noise_strength: float = Field(default=0.0, description="Cover noise strength (0=pure noise, 1=closest to src)")\n    inference_steps: int = Field(default=8, description="Number of diffusion inference steps")\n    infer_method: str = Field(default="ode", description="Diffusion inference method: \'ode\' or \'sde\'")\n    lm_cfg_scale: float = Field(default=2.0, description="LM classifier-free guidance scale")\n',
    '    audio_codes: str = Field(\n        default="", max_length=LIMITS.max_audio_codes_chars,\n        description="Pre-computed audio codes (bypass auto-conversion)",\n    )\n    cover_noise_strength: float = Field(\n        default=0.0, ge=0, le=1, description="Cover noise strength"\n    )\n    inference_steps: int = Field(\n        default=8, ge=1, le=LIMITS.max_inference_steps,\n        description="Number of diffusion inference steps",\n    )\n    infer_method: Literal["ode", "sde"] = Field(\n        default="ode", description="Diffusion inference method"\n    )\n    lm_cfg_scale: float = Field(\n        default=2.0, ge=0, le=20, description="LM classifier-free guidance scale"\n    )\n',
)

replace_once(
    "acestep/api/http/release_task_models.py",
    "from acestep.constants import DEFAULT_DIT_INSTRUCTION\n",
    "from acestep.constants import DEFAULT_DIT_INSTRUCTION\nfrom acestep.api.generation_resource_policy import LIMITS\n",
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    prompt: str = Field(default="", description="Text prompt describing the music (local/per-track description for lego SFT)")\n    global_caption: str = Field(default="", description="Global song description for SFT-stems lego tasks (full song context)")\n    lyrics: str = Field(default="", description="Lyric text")\n',
    '    prompt: str = Field(\n        default="", max_length=LIMITS.max_prompt_chars,\n        description="Text prompt describing the music",\n    )\n    global_caption: str = Field(\n        default="", max_length=LIMITS.max_prompt_chars,\n        description="Global song description",\n    )\n    lyrics: str = Field(\n        default="", max_length=LIMITS.max_lyrics_chars, description="Lyric text"\n    )\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    sample_query: str = Field(default="", description="Query/description for sample mode (use create_sample)")\n',
    '    sample_query: str = Field(\n        default="", max_length=LIMITS.max_sample_query_chars,\n        description="Query/description for sample mode",\n    )\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    model: Optional[str] = Field(default=None, description="Model name to use (e.g., \'acestep-v15-turbo\')")\n',
    '    model: Optional[str] = Field(\n        default=None, max_length=LIMITS.max_model_id_chars,\n        description="Approved model identifier",\n    )\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    inference_steps: int = 8\n    guidance_scale: float = 7.0\n',
    '    inference_steps: int = Field(default=8, ge=1, le=LIMITS.max_inference_steps)\n    guidance_scale: float = Field(default=7.0, ge=0, le=50)\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    audio_duration: Optional[float] = None\n    batch_size: Optional[int] = None\n',
    '    audio_duration: Optional[float] = Field(\n        default=None, gt=0, le=LIMITS.max_duration_seconds\n    )\n    batch_size: Optional[int] = Field(\n        default=None, ge=1, le=LIMITS.max_batch_size\n    )\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    audio_code_string: str = Field(\n        default="",\n',
    '    audio_code_string: str = Field(\n        default="",\n        max_length=LIMITS.max_audio_codes_chars,\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    task_type: str = "text2music"\n',
    '    task_type: Literal[\n        "text2music", "cover", "cover-nofsq", "repaint", "extract", "lego", "complete"\n    ] = "text2music"\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    audio_format: str = Field(\n        default="mp3",\n',
    '    audio_format: Literal["flac", "mp3", "opus", "aac", "wav", "wav32", "ogg", "m4a"] = Field(\n        default="mp3",\n',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '    lm_negative_prompt: str = "NO USER INPUT"\n',
    '    lm_negative_prompt: str = Field(\n        default="NO USER INPUT", max_length=LIMITS.max_prompt_chars\n    )\n',
)

# ---------------------------------------------------------------------------
# OpenRouter ingress, materialization, and response-mode timeout
# ---------------------------------------------------------------------------
replace_once(
    "acestep/openrouter_adapter.py",
    "from loguru import logger\n",
    "from loguru import logger\n\nfrom acestep.api.generation_resource_policy import (\n    GenerationLimitError,\n    decode_audio_base64,\n    generation_timeout_seconds,\n    read_json_object_limited,\n    validate_openrouter_request,\n)\n",
)
replace_once(
    "acestep/openrouter_adapter.py",
    'GENERATION_TIMEOUT = int(os.environ.get("ACESTEP_GENERATION_TIMEOUT", "600"))\n',
    'GENERATION_TIMEOUT = generation_timeout_seconds()\n',
)
replace_between(
    "acestep/openrouter_adapter.py",
    "def _base64_to_temp_file",
    "class _AudioBlob",
    '''def _base64_to_temp_file(b64_data: str, audio_format: str = "mp3") -> str:\n    """Decode bounded base64 audio and write it to a private temporary file."""\n    audio_format = audio_format.lower()\n    audio_bytes = decode_audio_base64(b64_data, audio_format)\n    fd, path = tempfile.mkstemp(suffix=f".{audio_format}", prefix="openrouter_audio_")\n    try:\n        with os.fdopen(fd, "wb") as file_obj:\n            file_obj.write(audio_bytes)\n            file_obj.flush()\n            os.fsync(file_obj.fileno())\n    except Exception:\n        try:\n            os.close(fd)\n        except OSError:\n            pass\n        try:\n            os.remove(path)\n        except OSError:\n            pass\n        raise\n    return path\n\n\n''',
)
replace_between(
    "acestep/openrouter_adapter.py",
    "def _materialize_audio_files",
    "def _cleanup_temp_paths",
    '''def _materialize_audio_files(blobs: List[_AudioBlob]) -> List[str]:\n    """Write validated deferred audio blobs, rolling back on any failure."""\n    paths: List[str] = []\n    try:\n        for blob in blobs:\n            paths.append(_base64_to_temp_file(blob.data, blob.format))\n    except Exception:\n        _cleanup_temp_paths(paths)\n        raise\n    return paths\n\n\n''',
)

stream_function = '''async def _openrouter_stream_generator(\n    rec: Any,\n    model_id: str,\n    audio_format: str,\n    *,\n    job_store: Any,\n    request: Optional[Request] = None,\n    timeout_seconds: Optional[float] = None,\n):\n    """Stream one job with disconnect cancellation and a wall-clock deadline."""\n    completion_id = _generate_completion_id()\n    created_timestamp = int(time.time())\n    timeout = float(timeout_seconds if timeout_seconds is not None else GENERATION_TIMEOUT)\n    deadline = time.monotonic() + max(0.001, timeout)\n    terminal = False\n\n    def _make_chunk(\n        content: Optional[str] = None,\n        role: Optional[str] = None,\n        audio: Optional[Any] = None,\n        finish_reason: Optional[str] = None,\n    ) -> str:\n        delta = {}\n        if role:\n            delta["role"] = role\n        if content is not None:\n            delta["content"] = content\n        if audio is not None:\n            delta["audio"] = audio\n        chunk = {\n            "id": completion_id,\n            "object": "chat.completion.chunk",\n            "created": created_timestamp,\n            "model": model_id,\n            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],\n        }\n        return f"data: {json.dumps(chunk)}\\n\\n"\n\n    async def _is_disconnected() -> bool:\n        if request is None:\n            return False\n        try:\n            return bool(await request.is_disconnected())\n        except Exception:\n            return False\n\n    yield _make_chunk(role="assistant", content="")\n    await asyncio.sleep(0)\n\n    try:\n        while True:\n            if await _is_disconnected():\n                job_store.request_cancel(rec.job_id, "Streaming client disconnected")\n                return\n\n            remaining = deadline - time.monotonic()\n            if remaining <= 0:\n                reason = f"Generation timed out after {timeout:g} seconds"\n                job_store.request_cancel(rec.job_id, reason)\n                yield _make_chunk(content=f"\\n\\nError: {reason}")\n                yield _make_chunk(finish_reason="error")\n                yield "data: [DONE]\\n\\n"\n                terminal = True\n                return\n\n            try:\n                msg = await asyncio.wait_for(\n                    rec.progress_queue.get(), timeout=min(2.0, remaining)\n                )\n            except asyncio.TimeoutError:\n                yield _make_chunk(content=".")\n                await asyncio.sleep(0)\n                continue\n\n            msg_type = msg.get("type")\n            if msg_type == "done":\n                break\n            if msg_type == "error":\n                yield _make_chunk(content=f"\\n\\nError: {msg.get('content', 'Unknown error')}")\n                yield _make_chunk(finish_reason="error")\n                yield "data: [DONE]\\n\\n"\n                terminal = True\n                return\n            if msg_type != "result":\n                continue\n\n            result = msg.get("result", {})\n            lm_content = _format_lm_content(result)\n            yield _make_chunk(content=f"\\n\\n{lm_content}")\n            await asyncio.sleep(0)\n\n            raw_audio_paths = result.get("raw_audio_paths", [])\n            if raw_audio_paths:\n                audio_path = raw_audio_paths[0]\n                if audio_path and os.path.exists(audio_path):\n                    b64_url = _audio_to_base64_url(audio_path, audio_format)\n                    if b64_url:\n                        yield _make_chunk(audio=[{\n                            "type": "audio_url",\n                            "audio_url": {"url": b64_url},\n                        }])\n                        await asyncio.sleep(0)\n\n            audio_codes = result.get("audio_codes")\n            if audio_codes:\n                yield _make_chunk(content=f"\\n\\n[audio_codes]{audio_codes}[/audio_codes]")\n                await asyncio.sleep(0)\n\n        yield _make_chunk(finish_reason="stop")\n        yield "data: [DONE]\\n\\n"\n        terminal = True\n    finally:\n        if not terminal and await _is_disconnected():\n            job_store.request_cancel(rec.job_id, "Streaming client disconnected")\n\n\n'''
replace_between(
    "acestep/openrouter_adapter.py",
    "async def _openrouter_stream_generator",
    "# =============================================================================\n# Router Factory",
    stream_function,
)
replace_once(
    "acestep/openrouter_adapter.py",
    '''        # Parse request\n        try:\n            body = await request.json()\n            req = ChatCompletionRequest(**body)\n        except Exception as e:\n            raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")\n''',
    '''        # Bound the body before JSON/Pydantic materialization.\n        try:\n            body = await read_json_object_limited(request)\n            req = ChatCompletionRequest(**body)\n            validate_openrouter_request(\n                req,\n                lm_initialized=bool(getattr(state, "_llm_initialized", False)),\n            )\n        except GenerationLimitError as exc:\n            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n        except Exception as exc:\n            raise HTTPException(status_code=400, detail=f"Invalid request format: {exc}") from exc\n''',
)
replace_once(
    "acestep/openrouter_adapter.py",
    '''        # Create job record first so we have a job_id for\n        # cleanup registration.\n        job_store = state.job_store\n        rec = job_store.create()\n\n        # Materialize audio blobs to temp files and register\n        # them for cleanup in one step — no leak window.\n        audio_paths = _materialize_audio_files(audio_blobs)\n        if audio_paths:\n            async with state.job_temp_files_lock:\n                state.job_temp_files.setdefault(\n                    rec.job_id, []\n                ).extend(audio_paths)\n''',
    '''        # Materialize only validated, bounded blobs.  Roll back all files on\n        # decode/write failure before a durable job record is created.\n        try:\n            audio_paths = _materialize_audio_files(audio_blobs)\n        except GenerationLimitError as exc:\n            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n        except Exception as exc:\n            raise HTTPException(status_code=400, detail=f"Invalid input audio: {exc}") from exc\n\n        job_store = state.job_store\n        rec = job_store.create()\n        job_store.set_deadline(rec.job_id, GENERATION_TIMEOUT)\n        if audio_paths:\n            async with state.job_temp_files_lock:\n                state.job_temp_files.setdefault(rec.job_id, []).extend(audio_paths)\n''',
)
replace_once(
    "acestep/openrouter_adapter.py",
    '''                _openrouter_stream_generator(rec, req.model, audio_format),\n                media_type="text/event-stream",\n''',
    '''                _openrouter_stream_generator(\n                    rec, req.model, audio_format,\n                    job_store=job_store, request=request,\n                ),\n                media_type="text/event-stream",\n''',
)
replace_once(
    "acestep/openrouter_adapter.py",
    '''            except asyncio.TimeoutError:\n                raise HTTPException(status_code=504, detail="Generation timeout")\n''',
    '''            except asyncio.TimeoutError as exc:\n                reason = f"Generation timed out after {GENERATION_TIMEOUT} seconds"\n                job_store.request_cancel(rec.job_id, reason)\n                raise HTTPException(status_code=504, detail=reason) from exc\n''',
)

# ---------------------------------------------------------------------------
# Job cancellation/deadline state and worker cooperation
# ---------------------------------------------------------------------------
replace_once(
    "acestep/api/jobs/store.py",
    '    progress_queue: Optional[asyncio.Queue] = None\n',
    '    progress_queue: Optional[asyncio.Queue] = None\n    cancel_requested: bool = False\n    cancel_reason: Optional[str] = None\n    deadline_monotonic: Optional[float] = None\n',
)
replace_between(
    "acestep/api/jobs/store.py",
    "    def mark_running",
    "    def mark_succeeded",
    '''    def mark_running(self, job_id: str) -> bool:\n        """Mark a queued job running unless cancellation already won the race."""\n        with self._lock:\n            record = self._jobs[job_id]\n            if record.cancel_requested or record.status == "failed":\n                return False\n            record.status = "running"\n            record.started_at = time.time()\n            record.progress = max(record.progress, 0.01)\n            record.stage = "running"\n            record.updated_at = time.time()\n            return True\n\n''',
)
replace_between(
    "acestep/api/jobs/store.py",
    "    def mark_succeeded",
    "    def mark_failed",
    '''    def mark_succeeded(self, job_id: str, result: Dict[str, Any]) -> bool:\n        """Mark success only when a timeout/disconnect has not cancelled the job."""\n        with self._lock:\n            record = self._jobs[job_id]\n            if record.cancel_requested or record.status == "failed":\n                if record.error is None:\n                    record.error = record.cancel_reason or "Generation cancelled"\n                return False\n            record.status = "succeeded"\n            record.finished_at = time.time()\n            record.result = result\n            record.error = None\n            record.progress = 1.0\n            record.stage = "succeeded"\n            record.updated_at = time.time()\n            return True\n\n''',
)
replace_once(
    "acestep/api/jobs/store.py",
    '''    def update_progress(self, job_id: str, progress: float, stage: Optional[str] = None) -> None:\n''',
    '''    def set_deadline(self, job_id: str, timeout_seconds: float) -> None:\n        """Attach a monotonic deadline used by response and worker paths."""\n        timeout = max(0.001, float(timeout_seconds))\n        with self._lock:\n            record = self._jobs[job_id]\n            record.deadline_monotonic = time.monotonic() + timeout\n\n    def request_cancel(self, job_id: str, reason: str) -> bool:\n        """Request cooperative cancellation and make the terminal state sticky."""\n        with self._lock:\n            record = self._jobs.get(job_id)\n            if record is None or record.status in ("succeeded", "failed"):\n                return False\n            record.cancel_requested = True\n            record.cancel_reason = reason or "Generation cancelled"\n            record.status = "failed"\n            record.finished_at = time.time()\n            record.result = None\n            record.error = record.cancel_reason\n            record.stage = "failed"\n            record.updated_at = time.time()\n            return True\n\n    def cancellation_reason(self, job_id: str) -> Optional[str]:\n        """Return cancellation reason and atomically expire elapsed deadlines."""\n        with self._lock:\n            record = self._jobs.get(job_id)\n            if record is None:\n                return "Generation job no longer exists"\n            if (\n                not record.cancel_requested\n                and record.deadline_monotonic is not None\n                and time.monotonic() >= record.deadline_monotonic\n            ):\n                record.cancel_requested = True\n                record.cancel_reason = "Generation deadline exceeded"\n                record.status = "failed"\n                record.finished_at = time.time()\n                record.result = None\n                record.error = record.cancel_reason\n                record.stage = "failed"\n                record.updated_at = time.time()\n            return record.cancel_reason if record.cancel_requested else None\n\n    def update_progress(self, job_id: str, progress: float, stage: Optional[str] = None) -> None:\n''',
)

new_process_queue = '''async def process_queue_item(\n    job_id: str,\n    req: Any,\n    app_state: Any,\n    store: Any,\n    run_one_job: Callable[[str, Any], Awaitable[None]],\n    cleanup_job_temp_files: Callable[[str], Awaitable[None]],\n) -> None:\n    """Process one queued item, skipping jobs cancelled before GPU admission."""\n    rec = store.get(job_id)\n    try:\n        async with app_state.pending_lock:\n            try:\n                app_state.pending_ids.remove(job_id)\n            except ValueError:\n                pass\n\n        reason = store.cancellation_reason(job_id)\n        if reason is None:\n            await run_one_job(job_id, req)\n\n        if rec and rec.progress_queue:\n            if rec.status == "succeeded" and rec.result:\n                await rec.progress_queue.put({"type": "result", "result": rec.result})\n            elif rec.status == "failed":\n                await rec.progress_queue.put({\n                    "type": "error",\n                    "content": rec.error or reason or "Generation failed",\n                })\n            await rec.progress_queue.put({"type": "done"})\n        if rec and rec.done_event:\n            rec.done_event.set()\n\n    except Exception as exc:\n        if rec and rec.status not in ("succeeded", "failed"):\n            store.mark_failed(job_id, str(exc))\n        if rec and rec.progress_queue:\n            await rec.progress_queue.put({"type": "error", "content": str(exc)})\n            await rec.progress_queue.put({"type": "done"})\n        if rec and rec.done_event:\n            rec.done_event.set()\n    finally:\n        await cleanup_job_temp_files(job_id)\n        app_state.job_queue.task_done()\n\n\n'''
replace_between(
    "acestep/api/jobs/worker_loops.py",
    "async def process_queue_item",
    "async def run_job_store_cleanup_loop",
    new_process_queue,
)
replace_once(
    "acestep/api/job_execution_runtime.py",
    '''    job_store.mark_running(job_id)\n    update_progress_job_cache_fn(\n''',
    '''    if not job_store.mark_running(job_id):\n        raise TimeoutError(job_store.cancellation_reason(job_id) or "Generation cancelled")\n    update_progress_job_cache_fn(\n''',
)
replace_once(
    "acestep/api/job_execution_runtime.py",
    '''        result = await loop.run_in_executor(executor, _blocking_generate)\n        job_store.mark_succeeded(job_id, result)\n        update_terminal_job_cache_fn(\n''',
    '''        result = await loop.run_in_executor(executor, _blocking_generate)\n        reason = job_store.cancellation_reason(job_id)\n        if reason is not None:\n            raise TimeoutError(reason)\n        if not job_store.mark_succeeded(job_id, result):\n            raise TimeoutError(job_store.cancellation_reason(job_id) or "Generation cancelled")\n        update_terminal_job_cache_fn(\n''',
)
replace_once(
    "acestep/api/job_blocking_generation.py",
    '''    def _progress_cb(value: float, desc: str = "") -> None:\n        now = time.time()\n''',
    '''    def _progress_cb(value: float, desc: str = "") -> None:\n        cancel_reason = store.cancellation_reason(job_id)\n        if cancel_reason is not None:\n            raise TimeoutError(cancel_reason)\n        now = time.time()\n''',
)

# ---------------------------------------------------------------------------
# Core defense-in-depth caps
# ---------------------------------------------------------------------------
replace_once(
    "acestep/core/generation/handler/task_utils.py",
    "from acestep.constants import TASK_INSTRUCTIONS\n",
    "from acestep.constants import TASK_INSTRUCTIONS\nfrom acestep.api.generation_resource_policy import LIMITS\n",
)
replace_once(
    "acestep/core/generation/handler/task_utils.py",
    '''        actual_seed_list: List[int] = []\n        seed_value_for_ui = ""\n''',
    '''        if not isinstance(actual_batch_size, int) or not (1 <= actual_batch_size <= LIMITS.max_batch_size):\n            raise ValueError(\n                f"actual_batch_size must be between 1 and {LIMITS.max_batch_size}"\n            )\n        actual_seed_list: List[int] = []\n        seed_value_for_ui = ""\n''',
)
replace_once(
    "acestep/core/generation/handler/task_utils.py",
    '''            duration_seconds = max(0.1, round(duration_seconds, 1))\n            frames = int(duration_seconds * 48000)\n''',
    '''            duration_seconds = min(\n                LIMITS.max_duration_seconds, max(0.1, round(duration_seconds, 1))\n            )\n            frames = int(duration_seconds * 48000)\n''',
)

# ---------------------------------------------------------------------------
# Custom Gradio API bounded body and expensive-parameter validation
# ---------------------------------------------------------------------------
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    "from fastapi.responses import FileResponse\n",
    "from fastapi.responses import FileResponse\n\nfrom acestep.api.generation_resource_policy import (\n    GenerationLimitError,\n    read_mapping_payload_limited,\n    validate_generation_work,\n    validate_param_object,\n    validate_task_id_query,\n    validate_text_inputs,\n)\n",
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''def verify_token_from_request(body: dict, authorization: Optional[str] = None) -> Optional[str]:\n''',
    '''async def _read_api_payload(request: Request) -> dict:\n    try:\n        return await read_mapping_payload_limited(request)\n    except GenerationLimitError as exc:\n        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n\n\ndef _enforce_limits(func, /, *args, **kwargs):\n    try:\n        return func(*args, **kwargs)\n    except GenerationLimitError as exc:\n        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n\n\ndef verify_token_from_request(body: dict, authorization: Optional[str] = None) -> Optional[str]:\n''',
)
old_body_parser = '''    content_type = (request.headers.get("content-type") or "").lower()\n\n    if "json" in content_type:\n        body = await request.json()\n    else:\n        form = await request.form()\n        body = {k: v for k, v in form.items()}\n'''
replace_all(
    "acestep/ui/gradio/api/api_routes.py",
    old_body_parser,
    "    body = await _read_api_payload(request)\n",
    expected=3,
)
# release_task has the same block without a blank line after content_type.
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''    content_type = (request.headers.get("content-type") or "").lower()\n    if "json" in content_type:\n        body = await request.json()\n    else:\n        form = await request.form()\n        body = {k: v for k, v in form.items()}\n\n    verify_token_from_request(body, authorization)\n    task_id = str(uuid4())\n''',
    '''    body = await _read_api_payload(request)\n\n    verify_token_from_request(body, authorization)\n    task_id = str(uuid4())\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''    results = []\n    for task_id in task_ids:\n''',
    '''    task_ids = _enforce_limits(validate_task_id_query, task_ids)\n\n    results = []\n    for task_id in task_ids:\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''    caption = body.get("prompt", "") or ""\n    lyrics = body.get("lyrics", "") or ""\n    temperature = float(body.get("temperature", 0.85))\n''',
    '''    caption = body.get("prompt", "") or ""\n    lyrics = body.get("lyrics", "") or ""\n    _enforce_limits(validate_text_inputs, prompt=caption, lyrics=lyrics)\n    temperature = float(body.get("temperature", 0.85))\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''    if isinstance(param_obj, str):\n        try:\n            param_obj = json.loads(param_obj)\n        except Exception:\n            param_obj = {}\n\n    # Helper to get param with aliases\n''',
    '''    if isinstance(param_obj, str):\n        try:\n            param_obj = json.loads(param_obj)\n        except Exception as exc:\n            raise HTTPException(status_code=400, detail="param_obj must be valid JSON") from exc\n    param_obj = _enforce_limits(validate_param_object, param_obj)\n\n    # Helper to get param with aliases\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''        lm_temperature = float(get_param("lm_temperature", "temperature", default=0.85) or 0.85)\n\n        # Process sample_mode: use LLM to auto-generate caption/lyrics/metas\n''',
    '''        lm_temperature = float(get_param("lm_temperature", "temperature", default=0.85) or 0.85)\n        _enforce_limits(\n            validate_text_inputs,\n            prompt=caption, lyrics=lyrics, sample_query=sample_query,\n        )\n        _enforce_limits(\n            validate_generation_work,\n            duration=get_param("audio_duration", "duration", default=-1),\n            batch_size=get_param("batch_size", default=2),\n            inference_steps=get_param("inference_steps", default=8),\n            task_type=get_param("task_type", default="text2music"),\n            infer_method=get_param("infer_method", default="ode"),\n            audio_format=get_param("audio_format", default="flac"),\n            seed=get_param("seed", default=-1),\n            lm_initialized=bool(llm_handler and llm_handler.llm_initialized),\n        )\n\n        # Process sample_mode: use LLM to auto-generate caption/lyrics/metas\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''        # Build generation params with alias support\n        params = GenerationParams(\n''',
    '''        _enforce_limits(\n            validate_text_inputs,\n            prompt=caption, lyrics=lyrics, sample_query=sample_query,\n        )\n        _enforce_limits(\n            validate_generation_work,\n            duration=sample_duration or get_param("audio_duration", "duration", default=-1),\n            batch_size=get_param("batch_size", default=2),\n            inference_steps=get_param("inference_steps", default=8),\n            task_type=get_param("task_type", default="text2music"),\n            infer_method=get_param("infer_method", default="ode"),\n            audio_format=get_param("audio_format", default="flac"),\n            seed=get_param("seed", default=-1),\n            lm_initialized=bool(llm_handler and llm_handler.llm_initialized),\n        )\n\n        # Build generation params with alias support\n        params = GenerationParams(\n''',
)
replace_once(
    "acestep/ui/gradio/api/api_routes.py",
    '''    except HTTPException:\n        raise\n    except Exception as e:\n''',
    '''    except GenerationLimitError as exc:\n        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc\n    except HTTPException:\n        raise\n    except Exception as e:\n''',
)

print("generation resource boundary integration applied")
