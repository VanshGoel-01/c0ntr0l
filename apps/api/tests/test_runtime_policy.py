from app.domain.runtime import (
    ActionHistoryItem,
    evaluate_loop,
    fingerprint,
    operation_fingerprint,
    sanitize_value,
)
from control_schemas import RuntimeDecision, RuntimePolicyMode


def history_item(operation: str, result: str, progress: bool) -> ActionHistoryItem:
    return ActionHistoryItem(operation, result, progress)


def test_operation_fingerprint_is_stable_and_redacts_secrets() -> None:
    first = operation_fingerprint(
        "tool",
        "Search",
        {"query": "  Indian   watershed monitoring ", "api_key": "private"},
    )
    second = operation_fingerprint(
        "tool",
        "search",
        {"api_key": "different-secret", "query": "Indian watershed monitoring"},
    )

    assert first == second
    assert sanitize_value({"token": "private"}) == {"token": "[REDACTED]"}


def test_third_no_progress_repeat_warns_and_fourth_is_blocked() -> None:
    operation = fingerprint("search:watershed")
    result = fingerprint({"results": []})
    two_calls = [history_item(operation, result, False) for _ in range(2)]
    three_calls = [history_item(operation, result, False) for _ in range(3)]

    warning = evaluate_loop(
        operation, two_calls, threshold=3, window_size=12, mode=RuntimePolicyMode.ENFORCE
    )
    blocked = evaluate_loop(
        operation,
        three_calls,
        threshold=3,
        window_size=12,
        mode=RuntimePolicyMode.ENFORCE,
    )

    assert warning.decision is RuntimeDecision.WARN
    assert blocked.decision is RuntimeDecision.BLOCK
    assert blocked.evidence["identical_results"] is True


def test_repetition_with_progress_warns_but_does_not_block() -> None:
    operation = fingerprint("read:next-page")
    history = [
        history_item(operation, fingerprint({"page": index}), True)
        for index in range(3)
    ]

    result = evaluate_loop(
        operation,
        history,
        threshold=3,
        window_size=12,
        mode=RuntimePolicyMode.ENFORCE,
    )

    assert result.decision is RuntimeDecision.WARN
    assert result.evidence["identical_results"] is False


def test_short_action_cycle_is_detected() -> None:
    search = fingerprint("search")
    read = fingerprint("read")
    history = [
        history_item(search, None, False),
        history_item(read, None, False),
        history_item(search, None, False),
        history_item(read, None, False),
        history_item(search, None, False),
        history_item(read, None, False),
    ]

    result = evaluate_loop(
        search,
        history,
        threshold=2,
        window_size=12,
        mode=RuntimePolicyMode.ENFORCE,
    )

    assert result.decision is RuntimeDecision.BLOCK
    assert result.evidence["cycle_length"] == 2


def test_observe_mode_never_blocks() -> None:
    operation = fingerprint("repeat")
    history = [history_item(operation, fingerprint("same"), False) for _ in range(4)]

    result = evaluate_loop(
        operation,
        history,
        threshold=3,
        window_size=12,
        mode=RuntimePolicyMode.OBSERVE,
    )

    assert result.decision is RuntimeDecision.ALLOW
