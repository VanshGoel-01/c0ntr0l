from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1, max_length=32_768)
    name: str | None = Field(default=None, min_length=1, max_length=128)


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    include_usage: bool = True


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    stream: bool = False
    stream_options: StreamOptions | None = None
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float | None = Field(default=None, ge=0, le=2)


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class FunctionCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    arguments: str


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "function"
    function: FunctionCall


class ResponseMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MessageRole = MessageRole.ASSISTANT
    content: str | None
    tool_calls: list[ToolCall] | None = None


class ChatChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = 0
    message: ResponseMessage
    finish_reason: str


class ChatCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice] = Field(min_length=1)
    usage: Usage


class ChatDeltaFunction(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str | None = None
    arguments: str | None = None


class ChatDeltaToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    index: int = Field(default=0, ge=0)
    id: str | None = None
    type: str | None = None
    function: ChatDeltaFunction | None = None


class ChatCompletionDelta(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    role: MessageRole | None = None
    content: str | None = None
    tool_calls: list[ChatDeltaToolCall] | None = None


class ChatCompletionChunkChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    index: int = Field(default=0, ge=0)
    delta: ChatCompletionDelta = Field(default_factory=ChatCompletionDelta)
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1, max_length=256)
    object: str = "chat.completion.chunk"
    created: int = Field(ge=0)
    model: str = Field(min_length=1, max_length=128)
    choices: list[ChatCompletionChunkChoice]
    usage: Usage | None = None

    @model_validator(mode="after")
    def require_delta_or_usage(self) -> "ChatCompletionChunk":
        if not self.choices and self.usage is None:
            raise ValueError("a stream chunk must include a choice or usage")
        return self
