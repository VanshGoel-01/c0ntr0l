from dataclasses import dataclass

from control_schemas import (
    ChatChoice,
    ChatCompletion,
    ChatCompletionChunk,
    FunctionCall,
    ResponseMessage,
    ToolCall,
    Usage,
)

from app.providers.errors import ProviderResponseError


@dataclass(slots=True)
class _ToolCallState:
    id: str = ""
    type: str = "function"
    name: str = ""
    arguments: str = ""


class ChatStreamAccumulator:
    def __init__(self) -> None:
        self._id: str | None = None
        self._created: int | None = None
        self._model: str | None = None
        self._content: list[str] = []
        self._tool_calls: dict[int, _ToolCallState] = {}
        self._finish_reason: str | None = None
        self._usage: Usage | None = None

    def add(self, chunk: ChatCompletionChunk) -> None:
        if self._id is not None and (
            chunk.id != self._id or chunk.model != self._model
        ):
            raise ProviderResponseError
        self._id = chunk.id
        self._created = chunk.created
        self._model = chunk.model
        if chunk.usage is not None:
            self._usage = chunk.usage

        if not chunk.choices:
            return
        choice = chunk.choices[0]
        if choice.delta.content is not None:
            self._content.append(choice.delta.content)
        for tool_call in choice.delta.tool_calls or []:
            state = self._tool_calls.setdefault(tool_call.index, _ToolCallState())
            if tool_call.id:
                state.id = tool_call.id
            if tool_call.type:
                state.type = tool_call.type
            if tool_call.function is not None:
                if tool_call.function.name:
                    state.name += tool_call.function.name
                if tool_call.function.arguments:
                    state.arguments += tool_call.function.arguments
        if choice.finish_reason is not None:
            self._finish_reason = choice.finish_reason

    def completion(self) -> ChatCompletion:
        if None in (
            self._id,
            self._created,
            self._model,
            self._finish_reason,
            self._usage,
        ):
            raise ProviderResponseError

        tool_calls = [
            ToolCall(
                id=state.id,
                type=state.type,
                function=FunctionCall(
                    name=state.name,
                    arguments=state.arguments,
                ),
            )
            for _, state in sorted(self._tool_calls.items())
            if state.id and state.name
        ]
        content = "".join(self._content) or None
        if content is None and not tool_calls:
            raise ProviderResponseError

        return ChatCompletion(
            id=self._id,
            created=self._created,
            model=self._model,
            choices=[
                ChatChoice(
                    message=ResponseMessage(
                        content=content,
                        tool_calls=tool_calls or None,
                    ),
                    finish_reason=self._finish_reason,
                )
            ],
            usage=self._usage,
        )
