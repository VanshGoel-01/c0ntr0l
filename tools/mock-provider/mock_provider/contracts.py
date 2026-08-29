from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    model: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    stream: bool = False
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float | None = Field(default=None, ge=0, le=2)


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


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
    created: int = 0
    model: str
    choices: list[ChatChoice]
    usage: Usage
