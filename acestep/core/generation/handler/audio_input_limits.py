"""Bound untrusted audio files before native decode and resampling.

The generation UI accepts file paths produced by Gradio.  Container metadata is
inspected before a decoder is allowed to allocate the full waveform, and the
decoders themselves receive a hard frame ceiling.  Environment variables may
tighten these limits but cannot widen the absolute ceilings in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any

import soundfile as sf


ABSOLUTE_MAX_AUDIO_FILE_BYTES = 256 * 1024 * 1024
ABSOLUTE_MAX_AUDIO_DURATION_SECONDS = 600.0
ABSOLUTE_MAX_AUDIO_SAMPLE_RATE = 192_000
ABSOLUTE_MAX_AUDIO_CHANNELS = 8
ABSOLUTE_MAX_DECODED_SAMPLES = 64_000_000
FFPROBE_TIMEOUT_SECONDS = 5.0
FFPROBE_OUTPUT_LIMIT_BYTES = 64 * 1024


class AudioInputLimitError(ValueError):
    """Raised when an input cannot be safely bounded before decoding."""


@dataclass(frozen=True)
class AudioInputLimits:
    max_file_bytes: int
    max_duration_seconds: float
    max_sample_rate: int
    max_channels: int
    max_decoded_samples: int


@dataclass(frozen=True)
class AudioFileMetadata:
    path: str
    file_size: int
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    probe: str


def _bounded_int_env(name: str, default: int, absolute: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise AudioInputLimitError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise AudioInputLimitError(f"{name} must be a positive integer")
    return min(value, absolute)


def _bounded_float_env(name: str, default: float, absolute: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise AudioInputLimitError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise AudioInputLimitError(f"{name} must be a positive number")
    return min(value, absolute)


def get_audio_input_limits() -> AudioInputLimits:
    """Return configured limits, never wider than the compiled ceilings."""

    return AudioInputLimits(
        max_file_bytes=_bounded_int_env(
            "ACESTEP_MAX_INPUT_AUDIO_BYTES",
            ABSOLUTE_MAX_AUDIO_FILE_BYTES,
            ABSOLUTE_MAX_AUDIO_FILE_BYTES,
        ),
        max_duration_seconds=_bounded_float_env(
            "ACESTEP_MAX_INPUT_AUDIO_SECONDS",
            ABSOLUTE_MAX_AUDIO_DURATION_SECONDS,
            ABSOLUTE_MAX_AUDIO_DURATION_SECONDS,
        ),
        max_sample_rate=_bounded_int_env(
            "ACESTEP_MAX_INPUT_AUDIO_SAMPLE_RATE",
            ABSOLUTE_MAX_AUDIO_SAMPLE_RATE,
            ABSOLUTE_MAX_AUDIO_SAMPLE_RATE,
        ),
        max_channels=_bounded_int_env(
            "ACESTEP_MAX_INPUT_AUDIO_CHANNELS",
            ABSOLUTE_MAX_AUDIO_CHANNELS,
            ABSOLUTE_MAX_AUDIO_CHANNELS,
        ),
        max_decoded_samples=_bounded_int_env(
            "ACESTEP_MAX_INPUT_AUDIO_SAMPLES",
            ABSOLUTE_MAX_DECODED_SAMPLES,
            ABSOLUTE_MAX_DECODED_SAMPLES,
        ),
    )


def _regular_file_size(audio_file: str, limits: AudioInputLimits) -> int:
    try:
        status = os.stat(audio_file, follow_symlinks=True)
    except OSError as exc:
        raise AudioInputLimitError("Audio file is not readable") from exc
    if not stat.S_ISREG(status.st_mode):
        raise AudioInputLimitError("Audio input must be a regular file")
    if status.st_size <= 0:
        raise AudioInputLimitError("Audio file is empty")
    if status.st_size > limits.max_file_bytes:
        raise AudioInputLimitError("Audio file exceeds the byte limit")
    return status.st_size


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AudioInputLimitError(f"Audio {field} is missing or invalid") from exc
    if parsed <= 0:
        raise AudioInputLimitError(f"Audio {field} is missing or invalid")
    return parsed


def _positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AudioInputLimitError(f"Audio {field} is missing or invalid") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise AudioInputLimitError(f"Audio {field} is missing or invalid")
    return parsed


def _probe_with_soundfile(audio_file: str, file_size: int) -> AudioFileMetadata:
    info = sf.info(audio_file)
    sample_rate = _positive_int(info.samplerate, "sample rate")
    channels = _positive_int(info.channels, "channel count")
    frames = _positive_int(info.frames, "frame count")
    duration = frames / sample_rate
    return AudioFileMetadata(
        path=audio_file,
        file_size=file_size,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
        duration_seconds=duration,
        probe="soundfile",
    )


def _probe_with_ffprobe(audio_file: str, file_size: int) -> AudioFileMetadata:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise AudioInputLimitError(
            "Audio format cannot be bounded because ffprobe is unavailable"
        )
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels,duration,nb_frames:format=duration",
        "-of",
        "json",
        audio_file,
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioInputLimitError("Audio metadata probe failed") from exc
    if completed.returncode != 0:
        raise AudioInputLimitError("Audio metadata probe rejected the file")
    if len(completed.stdout) > FFPROBE_OUTPUT_LIMIT_BYTES:
        raise AudioInputLimitError("Audio metadata probe output exceeded its limit")
    try:
        payload = json.loads(completed.stdout.decode("utf-8", errors="strict"))
        stream = payload["streams"][0]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise AudioInputLimitError("Audio metadata probe returned invalid data") from exc

    sample_rate = _positive_int(stream.get("sample_rate"), "sample rate")
    channels = _positive_int(stream.get("channels"), "channel count")

    duration_raw = stream.get("duration")
    if duration_raw in (None, "N/A", ""):
        duration_raw = (payload.get("format") or {}).get("duration")
    duration = _positive_float(duration_raw, "duration")

    frames_raw = stream.get("nb_frames")
    if frames_raw in (None, "N/A", ""):
        frames = max(1, math.ceil(duration * sample_rate))
    else:
        frames = _positive_int(frames_raw, "frame count")

    return AudioFileMetadata(
        path=audio_file,
        file_size=file_size,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
        duration_seconds=duration,
        probe="ffprobe",
    )


def _validate_metadata(
    metadata: AudioFileMetadata, limits: AudioInputLimits
) -> AudioFileMetadata:
    if metadata.sample_rate > limits.max_sample_rate:
        raise AudioInputLimitError("Audio sample rate exceeds the limit")
    if metadata.channels > limits.max_channels:
        raise AudioInputLimitError("Audio channel count exceeds the limit")
    if metadata.duration_seconds > limits.max_duration_seconds:
        raise AudioInputLimitError("Audio duration exceeds the limit")
    if metadata.frames * metadata.channels > limits.max_decoded_samples:
        raise AudioInputLimitError("Decoded audio sample budget would be exceeded")
    duration_from_frames = metadata.frames / metadata.sample_rate
    if duration_from_frames > limits.max_duration_seconds + (1.0 / metadata.sample_rate):
        raise AudioInputLimitError("Audio frame count exceeds the duration limit")
    return metadata


def validate_audio_file_limits(
    audio_file: str, limits: AudioInputLimits | None = None
) -> AudioFileMetadata:
    """Inspect an audio file without full waveform decode and enforce limits."""

    if not isinstance(audio_file, str) or not audio_file.strip():
        raise AudioInputLimitError("Audio path is required")
    normalized = str(Path(audio_file).expanduser())
    active_limits = limits or get_audio_input_limits()
    file_size = _regular_file_size(normalized, active_limits)
    try:
        metadata = _probe_with_soundfile(normalized, file_size)
    except (AudioInputLimitError, OSError, RuntimeError, ValueError):
        metadata = _probe_with_ffprobe(normalized, file_size)
    return _validate_metadata(metadata, active_limits)


def decode_frame_limit(metadata: AudioFileMetadata, limits: AudioInputLimits) -> int:
    """Return a one-frame-over read ceiling used to detect decoder overflow."""

    by_duration = math.floor(limits.max_duration_seconds * metadata.sample_rate)
    by_samples = limits.max_decoded_samples // metadata.channels
    allowed = min(by_duration, by_samples)
    if allowed <= 0:
        raise AudioInputLimitError("Audio decode frame budget is empty")
    return allowed + 1


def validate_decoded_audio(
    *, frames: int, channels: int, sample_rate: int, limits: AudioInputLimits
) -> None:
    """Recheck actual decoder output before copies, tensors, or resampling."""

    frames = _positive_int(frames, "decoded frame count")
    channels = _positive_int(channels, "decoded channel count")
    sample_rate = _positive_int(sample_rate, "decoded sample rate")
    if sample_rate > limits.max_sample_rate:
        raise AudioInputLimitError("Decoded audio sample rate exceeds the limit")
    if channels > limits.max_channels:
        raise AudioInputLimitError("Decoded audio channel count exceeds the limit")
    if frames / sample_rate > limits.max_duration_seconds:
        raise AudioInputLimitError("Decoded audio duration exceeds the limit")
    if frames * channels > limits.max_decoded_samples:
        raise AudioInputLimitError("Decoded audio sample budget was exceeded")
    projected_frames = math.ceil(frames * 48_000 / sample_rate)
    # Normalization always produces stereo: mono is duplicated and wider input
    # is truncated to two channels before resampling.
    projected_channels = 2
    if projected_frames * projected_channels > limits.max_decoded_samples:
        raise AudioInputLimitError("Resampled audio sample budget would be exceeded")
