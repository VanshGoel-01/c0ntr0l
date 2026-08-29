import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from control_schemas import RuntimeDecision, RuntimePolicyMode

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
_SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ActionHistoryItem:
    operation_fingerprint: str
    result_fingerprint: str | None
    progress: bool | None


@dataclass(frozen=True, slots=True)
class LoopEvaluation:
    decision: RuntimeDecision
    occurrence: int
    reason: str
    evidence: dict[str, object]


def sanitize_value(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_value(item_value, str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value[:100]]
    if isinstance(value, str):
        normalized = _SPACE_PATTERN.sub(" ", value.strip())
        return normalized[:2_000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2_000]


def fingerprint(value: Any) -> str:
    canonical = json.dumps(
        sanitize_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def operation_fingerprint(kind: str, name: str, arguments: dict[str, Any]) -> str:
    return fingerprint(
        {
            "kind": kind.lower().strip(),
            "name": name.lower().strip(),
            "arguments": arguments,
        }
    )


def _cycle_evidence(fingerprints: list[str]) -> tuple[int, int]:
    for cycle_length in range(1, min(3, len(fingerprints) // 2) + 1):
        pattern = fingerprints[-cycle_length:]
        repetitions = 1
        cursor = len(fingerprints) - cycle_length * 2
        while cursor >= 0 and fingerprints[cursor : cursor + cycle_length] == pattern:
            repetitions += 1
            cursor -= cycle_length
        if repetitions > 1:
            return cycle_length, repetitions
    return 0, 0


def evaluate_loop(
    operation: str,
    history: list[ActionHistoryItem],
    threshold: int,
    window_size: int,
    mode: RuntimePolicyMode,
) -> LoopEvaluation:
    recent = history[-window_size:]
    matching = [item for item in recent if item.operation_fingerprint == operation]
    occurrence = len(matching) + 1
    no_progress_repeats = sum(item.progress is False for item in matching)
    known_results = [
        item.result_fingerprint
        for item in matching
        if item.result_fingerprint is not None
    ]
    identical_results = (
        len(known_results) >= threshold
        and len(set(known_results[-threshold:])) == 1
    )
    sequence = [item.operation_fingerprint for item in recent] + [operation]
    cycle_length, cycle_repetitions = _cycle_evidence(sequence)
    exact_repeat_limit = occurrence > threshold
    cycle_history_size = max(0, cycle_length * cycle_repetitions - 1)
    cycle_history = recent[-cycle_history_size:] if cycle_history_size else []
    cycle_has_no_progress = bool(cycle_history) and all(
        item.progress is not True for item in cycle_history
    )
    cycle_limit = cycle_repetitions > threshold and cycle_has_no_progress
    no_progress = no_progress_repeats >= threshold or identical_results
    should_intervene = exact_repeat_limit and no_progress or cycle_limit

    evidence: dict[str, object] = {
        "occurrence": occurrence,
        "threshold": threshold,
        "window_size": window_size,
        "no_progress_repeats": no_progress_repeats,
        "identical_results": identical_results,
        "cycle_length": cycle_length,
        "cycle_repetitions": cycle_repetitions,
        "cycle_has_no_progress": cycle_has_no_progress,
    }

    if should_intervene and mode is RuntimePolicyMode.ENFORCE:
        reason = (
            "Repeated action produced no meaningful progress"
            if exact_repeat_limit
            else f"Repeated action cycle of length {cycle_length} detected"
        )
        return LoopEvaluation(RuntimeDecision.BLOCK, occurrence, reason, evidence)

    if occurrence >= threshold or cycle_repetitions >= threshold:
        reason = "Action repetition is approaching the configured limit"
        if should_intervene and mode is RuntimePolicyMode.OBSERVE:
            reason = "Loop observed; observe mode does not interrupt execution"
            return LoopEvaluation(RuntimeDecision.ALLOW, occurrence, reason, evidence)
        return LoopEvaluation(RuntimeDecision.WARN, occurrence, reason, evidence)

    return LoopEvaluation(
        RuntimeDecision.ALLOW,
        occurrence,
        "No loop policy was triggered",
        evidence,
    )
