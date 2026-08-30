import pytest
from app.domain.streaming import ChatStreamAccumulator
from app.providers.errors import ProviderResponseError
from control_schemas import ChatCompletionChunk, Usage


def chunk(value: dict[str, object]) -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-stream",
            "created": 1,
            "model": "mock-model",
            **value,
        }
    )


def test_accumulator_reconstructs_content_and_usage() -> None:
    accumulator = ChatStreamAccumulator()
    accumulator.add(
        chunk({"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]})
    )
    accumulator.add(
        chunk(
            {
                "choices": [{"delta": {"content": " world"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 2,
                    "total_tokens": 4,
                },
            }
        )
    )

    completion = accumulator.completion()

    assert completion.choices[0].message.content == "hello world"
    assert completion.usage.total_tokens == 4


def test_accumulator_reconstructs_split_tool_arguments() -> None:
    accumulator = ChatStreamAccumulator()
    accumulator.add(
        chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q":',
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            }
        )
    )
    accumulator.add(
        chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '"water"}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                },
            }
        )
    )

    tool_call = accumulator.completion().choices[0].message.tool_calls[0]

    assert tool_call.function.name == "search"
    assert tool_call.function.arguments == '{"q":"water"}'


def test_accumulator_requires_final_usage() -> None:
    accumulator = ChatStreamAccumulator()
    accumulator.add(
        chunk({"choices": [{"delta": {"content": "partial"}, "finish_reason": "stop"}]})
    )

    with pytest.raises(ProviderResponseError):
        accumulator.completion()


def test_accumulator_accepts_separate_usage_only_chunk() -> None:
    accumulator = ChatStreamAccumulator()
    accumulator.add(
        chunk({"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]})
    )
    accumulator.add(chunk({"choices": [{"delta": {}, "finish_reason": "stop"}]}))
    accumulator.add(
        chunk(
            {
                "choices": [],
                "usage": Usage(
                    prompt_tokens=2,
                    completion_tokens=1,
                    total_tokens=3,
                ),
            }
        )
    )

    completion = accumulator.completion()

    assert completion.choices[0].message.content == "hello"
    assert completion.usage.total_tokens == 3
