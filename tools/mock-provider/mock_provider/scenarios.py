import hashlib
import json
from enum import StrEnum

from mock_provider.contracts import (
    ChatChoice,
    ChatCompletion,
    ChatRequest,
    FunctionCall,
    ResponseMessage,
    ToolCall,
    Usage,
)


class MockScenario(StrEnum):
    NORMAL = "normal"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    REPEATED_TOOL = "repeated_tool"


def completion_id(request: ChatRequest, scenario: MockScenario) -> str:
    payload = {
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "model": request.model,
        "scenario": scenario,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"chatcmpl-mock-{digest}"


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def calculate_usage(request: ChatRequest, output_text: str) -> Usage:
    prompt_tokens = sum(
        estimate_tokens(message.content) for message in request.messages
    )
    completion_tokens = min(estimate_tokens(output_text), request.max_tokens)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def build_completion(request: ChatRequest, scenario: MockScenario) -> ChatCompletion:
    if scenario is MockScenario.REPEATED_TOOL:
        output_text = '{"resource":"demo"}'
        message = ResponseMessage(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_mock_lookup_status",
                    function=FunctionCall(
                        name="lookup_status",
                        arguments=output_text,
                    ),
                )
            ],
        )
        finish_reason = "tool_calls"
    else:
        output_text = (
            "Deterministic mock completion: the request reached the provider "
            "without using paid model credits."
        )
        message = ResponseMessage(content=output_text)
        finish_reason = "stop"

    return ChatCompletion(
        id=completion_id(request, scenario),
        model=request.model,
        choices=[
            ChatChoice(
                message=message,
                finish_reason=finish_reason,
            )
        ],
        usage=calculate_usage(request, output_text),
    )


def stream_events(completion: ChatCompletion) -> list[str]:
    choice = completion.choices[0]
    events: list[dict[str, object]] = [
        {
            "id": completion.id,
            "object": "chat.completion.chunk",
            "created": completion.created,
            "model": completion.model,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        }
    ]

    if choice.message.content is not None:
        words = choice.message.content.split()
        for index, word in enumerate(words):
            content = word if index == 0 else f" {word}"
            events.append(
                {
                    "id": completion.id,
                    "object": "chat.completion.chunk",
                    "created": completion.created,
                    "model": completion.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
            )
    else:
        events.append(
            {
                "id": completion.id,
                "object": "chat.completion.chunk",
                "created": completion.created,
                "model": completion.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                tool_call.model_dump(mode="json")
                                for tool_call in (choice.message.tool_calls or [])
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )

    events.append(
        {
            "id": completion.id,
            "object": "chat.completion.chunk",
            "created": completion.created,
            "model": completion.model,
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": choice.finish_reason}
            ],
            "usage": completion.usage.model_dump(),
        }
    )
    return [f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events]
