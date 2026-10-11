"""OpenRouter API compatible Pydantic models for ACE-Step.

Request fields carry absolute schema ceilings; the route applies the narrower
hardware-aware budget before decoding audio or queueing generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from acestep.api.generation_resource_policy import (
    HARD_MAX_AUDIO_BYTES,
    HARD_MAX_AUDIO_CODES_CHARS,
    HARD_MAX_BATCH_SIZE,
    HARD_MAX_DURATION_SECONDS,
    HARD_MAX_INFERENCE_STEPS,
    HARD_MAX_LYRICS_CHARS,
    HARD_MAX_MESSAGE_COUNT,
    HARD_MAX_TEXT_CHARS,
)

_MAX_AUDIO_BASE64_CHARS = 4 * ((HARD_MAX_AUDIO_BYTES + 2) // 3) + 128
AudioFormat = Literal["mp3", "wav", "wav32", "flac", "ogg", "opus", "aac", "m4a"]
TaskType = Literal[
    "text2music",
    "cover",
    "cover-nofsq",
    "repaint",
    "extract",
    "lego",
    "complete",
]


class AudioInputContent(BaseModel):
    """One bounded base64 audio input."""

    data: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_AUDIO_BASE64_CHARS,
        description="Base64-encoded audio data",
    )
    format: AudioFormat = Field(default="mp3", description="Audio format")


class TextContent(BaseModel):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str = Field(
        ...,
        max_length=HARD_MAX_TEXT_CHARS,
        description="Text content",
    )


class AudioContent(BaseModel):
    """Audio input content block."""

    type: Literal["input_audio"] = "input_audio"
    input_audio: AudioInputContent


ContentPart = Union[TextContent, AudioContent, Dict[str, Any]]


class ChatMessage(BaseModel):
    """A single bounded message in the chat conversation."""

    role: Literal["system", "user", "assistant"] = Field(
        ...,
        description="Message role",
    )
    content: Union[str, List[ContentPart]] = Field(
        ...,
        description="Message content",
    )
    name: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Optional name for the message author",
    )


class AudioConfig(BaseModel):
    """Audio generation configuration."""

    duration: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=HARD_MAX_DURATION_SECONDS,
        description="Target audio duration in seconds",
    )
    format: AudioFormat = Field(default="mp3", description="Output audio format")
    bpm: Optional[int] = Field(default=None, ge=1, le=1000)
    key_scale: Optional[str] = Field(default=None, max_length=256)
    time_signature: Optional[str] = Field(default=None, max_length=64)
    vocal_language: Optional[str] = Field(default=None, max_length=64)
    instrumental: Optional[bool] = Field(default=None)


class ChatCompletionRequest(BaseModel):
    """OpenRouter-compatible request with hard schema ceilings."""

    model: str = Field(..., min_length=1, max_length=256)
    messages: List[ChatMessage] = Field(
        ...,
        min_length=1,
        max_length=HARD_MAX_MESSAGE_COUNT,
    )

    modalities: Optional[List[str]] = Field(default=None, max_length=8)
    audio_config: Optional[AudioConfig] = None

    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    top_k: Optional[int] = Field(default=None, ge=0, le=1000)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    seed: Optional[Union[int, str]] = None

    thinking: Optional[bool] = None
    guidance_scale: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    batch_size: Optional[int] = Field(
        default=None,
        ge=1,
        le=HARD_MAX_BATCH_SIZE,
    )

    lyrics: str = Field(default="", max_length=HARD_MAX_LYRICS_CHARS)
    sample_mode: bool = False
    use_format: bool = False
    use_cot_caption: bool = True
    use_cot_language: bool = True

    task_type: TaskType = "text2music"

    repainting_start: float = Field(default=0.0, ge=0.0, le=HARD_MAX_DURATION_SECONDS)
    repainting_end: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=HARD_MAX_DURATION_SECONDS,
    )
    audio_cover_strength: float = Field(default=1.0, ge=0.0, le=1.0)

    audio_codes: str = Field(default="", max_length=HARD_MAX_AUDIO_CODES_CHARS)
    cover_noise_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    inference_steps: int = Field(
        default=8,
        ge=1,
        le=HARD_MAX_INFERENCE_STEPS,
    )
    infer_method: Literal["ode", "sde"] = "ode"
    lm_cfg_scale: float = Field(default=2.0, ge=0.0, le=100.0)
    use_cot_metas: Optional[bool] = None

    class Config:
        extra = "allow"


class AudioOutputUrl(BaseModel):
    url: str


class AudioOutput(BaseModel):
    type: Literal["audio_url"] = "audio_url"
    audio_url: AudioOutputUrl


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    audio: Optional[List[AudioOutput]] = None
    audio_codes: Optional[str] = None


class Choice(BaseModel):
    index: int = 0
    message: AssistantMessage
    finish_reason: Literal["stop", "length", "content_filter", "error"] = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage = Field(default_factory=Usage)
    system_fingerprint: Optional[str] = None


class DeltaContent(BaseModel):
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None
    audio: Optional[List[AudioOutput]] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaContent
    finish_reason: Optional[
        Literal["stop", "length", "content_filter", "error"]
    ] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]


class ModelPricing(BaseModel):
    prompt: str = "0"
    completion: str = "0"
    request: str = "0"
    image: str = "0"


class ModelInfo(BaseModel):
    id: str
    name: str
    created: int
    input_modalities: List[str] = Field(default_factory=lambda: ["text"])
    output_modalities: List[str] = Field(default_factory=lambda: ["audio", "text"])
    context_length: int = 4096
    max_output_length: int = 300
    pricing: ModelPricing = Field(default_factory=ModelPricing)
    description: Optional[str] = None
    architecture: Optional[Dict[str, Any]] = None


class ModelsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelInfo] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    message: str
    type: str = "invalid_request_error"
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
