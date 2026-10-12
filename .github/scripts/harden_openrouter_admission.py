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
        raise RuntimeError(f"{rel}: expected one target, found {count}: {old[:160]!r}")
    write(rel, text.replace(old, new, 1))


def replace_between(rel: str, start: str, end: str, replacement: str) -> None:
    text = read(rel)
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{rel}: start marker not found: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{rel}: end marker not found: {end!r}")
    write(rel, text[:start_index] + replacement + text[end_index:])


# Preserve the documented -1 automatic-duration sentinel while rejecting every
# other non-positive explicit value at the typed request boundary.
replace_once(
    "acestep/api/http/release_task_models.py",
    "from pydantic import BaseModel, Field\n",
    "from pydantic import BaseModel, Field, field_validator\n",
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '''    audio_duration: Optional[float] = Field(
        default=None, gt=0, le=LIMITS.max_duration_seconds
    )
''',
    '''    audio_duration: Optional[float] = Field(
        default=None, ge=-1, le=LIMITS.max_duration_seconds
    )
''',
)
replace_once(
    "acestep/api/http/release_task_models.py",
    '''    class Config:
        """Legacy pydantic config preserving prior population semantics."""
''',
    '''    @field_validator("audio_duration")
    @classmethod
    def validate_audio_duration_sentinel(cls, value: Optional[float]) -> Optional[float]:
        """Accept only omitted, positive, or the documented -1 auto sentinel."""
        if value is None or value == -1 or value > 0:
            return value
        raise ValueError("audio_duration must be -1 (auto) or greater than zero")

    class Config:
        """Legacy pydantic config preserving prior population semantics."""
''',
)

# Serialize the bounded OpenRouter-only preprocessing window. This is not a
# second scheduler: all admitted jobs still enter the one existing GPU queue.
replace_once(
    "acestep/api/lifespan_runtime.py",
    '''    app.state.pending_ids = deque()
    app.state.pending_lock = asyncio.Lock()
    app.state.job_temp_files = {}
''',
    '''    app.state.pending_ids = deque()
    app.state.pending_lock = asyncio.Lock()
    app.state.openrouter_prequeue_lock = asyncio.Lock()
    app.state.job_temp_files = {}
''',
)

# Reuse the same identity/state guarded rollback primitive as the separate
# release-task admission candidate. Applying that branch later should resolve
# to one identical method rather than two semantics.
replace_once(
    "acestep/api/jobs/store.py",
    '''        with self._lock:
            self._jobs[job_id] = record
        return record

    def create_with_id(self, job_id: str, env: str = "development") -> _JobRecord:
''',
    '''        with self._lock:
            self._jobs[job_id] = record
        return record

    def discard_unsubmitted(self, record: _JobRecord) -> bool:
        """Undo failed admission without removing replacements or running work."""
        with self._lock:
            current = self._jobs.get(record.job_id)
            if current is not record or current.status != "queued":
                return False
            del self._jobs[record.job_id]
            return True

    def create_with_id(self, job_id: str, env: str = "development") -> _JobRecord:
''',
)

# Atomic OpenRouter admission owns pending/temp metadata until put_nowait
# succeeds. Every pre-admission failure removes request-owned files and records.
replace_once(
    "acestep/openrouter_adapter.py",
    '''def _cleanup_temp_paths(paths: List[str]) -> None:
    """Remove temporary files, ignoring errors."""
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass


def _extract_tagged_content''',
    '''def _cleanup_temp_paths(paths: List[str]) -> None:
    """Remove temporary files, ignoring errors."""
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass


async def _admit_openrouter_job(
    state: Any,
    job_store: Any,
    gen_request: Any,
    audio_paths: List[str],
    *,
    streaming: bool,
):
    """Atomically publish one prepared OpenRouter job or roll it back fully."""
    queue_ref: asyncio.Queue = state.job_queue
    record = None
    admitted = False
    try:
        # Match the maintained release-task lock order. There is no await from
        # the capacity recheck through put_nowait on this event loop.
        async with state.pending_lock:
            async with state.job_temp_files_lock:
                if queue_ref.full():
                    raise HTTPException(status_code=429, detail="Server busy: queue is full")

                record = job_store.create()
                try:
                    job_store.set_deadline(record.job_id, GENERATION_TIMEOUT)
                    if streaming:
                        record.progress_queue = asyncio.Queue()
                    else:
                        record.done_event = asyncio.Event()
                    if audio_paths:
                        state.job_temp_files[record.job_id] = list(audio_paths)
                    state.pending_ids.append(record.job_id)
                    queue_ref.put_nowait((record.job_id, gen_request))
                    admitted = True
                except BaseException as exc:
                    try:
                        state.pending_ids.remove(record.job_id)
                    except ValueError:
                        pass
                    state.job_temp_files.pop(record.job_id, None)
                    job_store.discard_unsubmitted(record)
                    if isinstance(exc, asyncio.QueueFull):
                        raise HTTPException(
                            status_code=429, detail="Server busy: queue is full"
                        ) from exc
                    raise
        return record
    finally:
        if not admitted:
            _cleanup_temp_paths(audio_paths)


def _extract_tagged_content''',
)

replacement = '''        # Serialize only bounded OpenRouter preprocessing. Admitted work still
        # uses the existing shared GPU queue and worker lifecycle.
        job_queue = state.job_queue
        prequeue_lock = getattr(state, "openrouter_prequeue_lock", None)
        if prequeue_lock is None:
            raise HTTPException(status_code=503, detail="OpenRouter admission is unavailable")

        audio_config = req.audio_config or AudioConfig()
        audio_format = audio_config.format or DEFAULT_AUDIO_FORMAT
        audio_paths: List[str] = []
        rec = None
        try:
            async with prequeue_lock:
                # Recheck before any decode, file write, or cover conversion.
                if job_queue.full():
                    raise HTTPException(status_code=429, detail="Server busy: queue is full")

                audio_paths = _materialize_audio_files(audio_blobs)
                reference_audio_path = None
                src_audio_path = None
                src_audio_task_types = {
                    "cover", "cover-nofsq", "repaint", "lego",
                    "extract", "complete",
                }
                if audio_paths:
                    if req.task_type in src_audio_task_types:
                        src_audio_path = audio_paths[0]
                        if len(audio_paths) > 1:
                            reference_audio_path = audio_paths[1]
                    else:
                        reference_audio_path = audio_paths[0]

                # Preserve the existing cover compatibility behavior, but cap
                # concurrent pre-queue conversion at one per process.
                resolved_audio_codes = req.audio_codes
                if (
                    src_audio_path
                    and not resolved_audio_codes
                    and req.task_type == "cover"
                ):
                    handler = getattr(state, "handler", None)
                    if handler and hasattr(handler, "convert_src_audio_to_codes"):
                        try:
                            codes_str = await asyncio.to_thread(
                                handler.convert_src_audio_to_codes,
                                src_audio_path,
                            )
                            if codes_str and not codes_str.startswith("❌"):
                                resolved_audio_codes = codes_str
                        except Exception as exc:
                            logger.error(
                                "Auto-cover audio transcoding failed for {}: {}",
                                src_audio_path,
                                exc,
                            )

                gen_request = _to_generate_music_request(
                    req,
                    prompt,
                    lyrics,
                    sample_query,
                    reference_audio_path,
                    src_audio_path,
                    audio_codes=resolved_audio_codes,
                )
                rec = await _admit_openrouter_job(
                    state,
                    state.job_store,
                    gen_request,
                    audio_paths,
                    streaming=req.stream,
                )
        except BaseException:
            # The admission helper owns cleanup after it starts. Failures before
            # it returns are safely idempotent here as well.
            if rec is None:
                _cleanup_temp_paths(audio_paths)
            raise

        if req.stream:
            return StreamingResponse(
                _openrouter_stream_generator(
                    rec,
                    req.model,
                    audio_format,
                    job_store=state.job_store,
                    request=request,
                ),
                media_type="text/event-stream",
            )
        else:
'''
replace_between(
    "acestep/openrouter_adapter.py",
    "        # Check queue capacity — still no temp files on disk.\n",
    "            # Wait for completion with timeout\n",
    replacement,
)

print("OpenRouter preprocessing, admission rollback, and duration compatibility integrated")
