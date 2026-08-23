from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import cast

from pydantic import JsonValue, TypeAdapter

from app.schemas.alignment import (
    CanonicalContentResult,
    CanonicalEvent,
    CanonicalizationPolicy,
    CanonicalTrajectory,
    EventKind,
    EventMetrics,
    ScrubberCount,
    ScrubberScope,
    StringScrubberRule,
)
from app.schemas.trace_contract import (
    CanonicalEventStatus,
    CanonicalMessage,
    CanonicalRunRow,
    SourceRef,
)

_json_value_adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MIN_BIGRAM_TOKENS = 2
_NOT_JSON = object()


@dataclass(slots=True)
class _NormalizationAudit:
    notes: list[str] = field(default_factory=list)
    scrubber_counts: Counter[str] = field(default_factory=Counter)
    ignored_fields: int = 0
    oversized: bool = False


@dataclass(frozen=True, slots=True)
class _PresetRule:
    id: str
    pattern: re.Pattern[str]
    replacement: str


_VOLATILE_PRESET = (
    _PresetRule(
        "iso_timestamp",
        re.compile(
            r"(?<!\d)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})(?!\d)"
        ),
        "<ISO_TIMESTAMP>",
    ),
    _PresetRule(
        "temporary_path",
        re.compile(r"(?<![\w/])(?:/private)?/tmp/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"),
        "<TMP_PATH>",
    ),
    _PresetRule(
        "process_id",
        re.compile(r"(?i)(\bpid\s*[=:]\s*)\d+\b"),
        r"\1<PID>",
    ),
    _PresetRule(
        "localhost_port",
        re.compile(r"\b((?:localhost|127\.0\.0\.1|\[::1\]):)\d{2,5}\b", re.IGNORECASE),
        r"\1<PORT>",
    ),
    _PresetRule(
        "uuid",
        re.compile(
            r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
        ),
        "<UUID>",
    ),
    _PresetRule(
        "request_hex",
        re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{24,64}(?![0-9a-f])"),
        "<REQUEST_HEX>",
    ),
)


def canonical_policy_hash(policy: CanonicalizationPolicy) -> str:
    return hashlib.sha256(_canonical_json_bytes(policy.model_dump(mode="json"))).hexdigest()


def canonical_event_signature(
    event: CanonicalEvent,
    policy: CanonicalizationPolicy,
) -> str:
    return _event_signature(
        kind=event.kind,
        actor=event.actor,
        call_id=event.call_id,
        name=event.name,
        status=event.status,
        content=event.content,
        policy=policy,
    )


def canonicalize_run(
    run: CanonicalRunRow,
    policy: CanonicalizationPolicy | None = None,
) -> CanonicalTrajectory:
    """Flatten and canonicalize a run-row without accessing persistence or global state."""
    active_policy = policy or CanonicalizationPolicy()
    events: list[CanonicalEvent] = []
    ignored_fields = 0
    for message in run.messages:
        flattened = _flatten_message(message, start_index=len(events), policy=active_policy)
        events.extend(flattened)
        ignored_fields += sum(
            1
            for event in flattened
            for note in event.normalization_notes
            if note.startswith("ignored:")
        )
    return CanonicalTrajectory(
        trace_id=run.trace_id,
        policy_hash=canonical_policy_hash(active_policy),
        events=events,
        ignored_difference_candidates=ignored_fields,
    )


def canonicalize_content(
    value: object,
    policy: CanonicalizationPolicy | None = None,
    *,
    scope: ScrubberScope = "all",
) -> CanonicalContentResult:
    """Canonicalize an adapter value, reducing binary payloads to auditable metadata."""
    active_policy = policy or CanonicalizationPolicy()
    audit = _NormalizationAudit()
    normalized = _normalize_value(
        value,
        path="$",
        scope=scope,
        policy=active_policy,
        audit=audit,
    )
    return CanonicalContentResult(
        content=_json_value_adapter.validate_python(normalized),
        normalization_notes=audit.notes,
        scrubber_counts=[
            ScrubberCount(rule_id=rule_id, count=count)
            for rule_id, count in sorted(audit.scrubber_counts.items())
        ],
        ignored_fields=audit.ignored_fields,
        oversized=audit.oversized,
    )


def assistant_text_similarity(left: CanonicalEvent, right: CanonicalEvent) -> float:
    """Return deterministic token-bigram or Unicode char-4-gram Jaccard similarity."""
    left_text = _text_content(left.content)
    right_text = _text_content(right.content)
    left_words = [item.casefold() for item in _WORD_RE.findall(left_text)]
    right_words = [item.casefold() for item in _WORD_RE.findall(right_text)]
    if len(left_words) >= _MIN_BIGRAM_TOKENS and len(right_words) >= _MIN_BIGRAM_TOKENS:
        left_features = {"\0".join(items) for items in pairwise(left_words)}
        right_features = {"\0".join(items) for items in pairwise(right_words)}
    else:
        left_features = _character_ngrams(left_text.casefold(), 4)
        right_features = _character_ngrams(right_text.casefold(), 4)
    if not left_features and not right_features:
        return 1.0 if left_text == right_text else 0.0
    union = left_features | right_features
    return len(left_features & right_features) / len(union) if union else 0.0


def assistant_events_are_near_match(
    left: CanonicalEvent,
    right: CanonicalEvent,
    policy: CanonicalizationPolicy,
) -> tuple[bool, float]:
    if left.kind != "assistant" or right.kind != "assistant" or left.status != right.status:
        return False, 0.0
    left_text = _text_content(left.content)
    right_text = _text_content(right.content)
    if left_text == right_text:
        return True, 1.0
    if min(len(left_text), len(right_text)) < policy.assistant_short_text_exact_chars:
        return False, 0.0
    length_ratio = min(len(left_text), len(right_text)) / max(len(left_text), len(right_text))
    if length_ratio < policy.assistant_near_match_min_length_ratio:
        return False, 0.0
    similarity = assistant_text_similarity(left, right)
    return similarity >= policy.assistant_near_match_threshold, similarity


def _flatten_message(
    message: CanonicalMessage,
    *,
    start_index: int,
    policy: CanonicalizationPolicy,
) -> list[CanonicalEvent]:
    raw_tool_calls = _tool_calls(message.tool_calls)
    result: list[CanonicalEvent] = []
    message_kind = _message_kind(message)
    if raw_tool_calls and _has_visible_content(message.content):
        result.append(
            _build_event(
                index=start_index,
                kind="assistant",
                actor=message.role,
                call_id=message.tool_call_id,
                parent_ref=message.parent_event_id,
                name=message.name,
                status=message.status,
                content=message.content,
                message=message,
                scope="assistant",
                policy=policy,
            )
        )
    for call in raw_tool_calls:
        function = call.get("function")
        function_map = function if isinstance(function, Mapping) else {}
        name = _optional_string(function_map.get("name")) or _optional_string(call.get("name"))
        arguments = function_map.get("arguments", call.get("arguments"))
        result.append(
            _build_event(
                index=start_index + len(result),
                kind="tool_call",
                actor=message.role,
                call_id=_optional_string(call.get("id")) or message.tool_call_id,
                parent_ref=message.parent_event_id,
                name=name or message.name,
                status=message.status,
                content=_parse_json_string(arguments),
                message=message,
                scope="tool_arguments",
                policy=policy,
            )
        )
    if not raw_tool_calls:
        scope: ScrubberScope = "tool_result" if message_kind == "tool_result" else "assistant"
        result.append(
            _build_event(
                index=start_index,
                kind=message_kind,
                actor=message.role,
                call_id=message.tool_call_id,
                parent_ref=message.parent_event_id,
                name=message.name,
                status=message.status,
                content=message.content,
                message=message,
                scope=scope,
                policy=policy,
            )
        )
    return result


def _build_event(
    *,
    index: int,
    kind: EventKind,
    actor: str | None,
    call_id: str | None,
    parent_ref: str | None,
    name: str | None,
    status: CanonicalEventStatus,
    content: object,
    message: CanonicalMessage,
    scope: ScrubberScope,
    policy: CanonicalizationPolicy,
) -> CanonicalEvent:
    audit = _NormalizationAudit()
    normalized = _normalize_value(content, path="$", scope=scope, policy=policy, audit=audit)
    canonical_content = _json_value_adapter.validate_python(normalized)
    timestamp = _parse_timestamp(message.timestamp, audit)
    signature = _event_signature(
        kind=kind,
        actor=actor,
        call_id=call_id,
        name=name,
        status=status,
        content=canonical_content,
        policy=policy,
    )
    return CanonicalEvent(
        index=index,
        kind=kind,
        actor=actor,
        call_id=call_id,
        parent_ref=parent_ref,
        name=name,
        status=status,
        content=canonical_content,
        metrics=EventMetrics(
            timestamp=timestamp,
            latency_ms=message.latency_ms,
            tokens_in=message.tokens_in,
            tokens_out=message.tokens_out,
            cost_usd=message.cost_usd,
        ),
        signature=signature,
        raw_ref=_source_ref_text(message.source_ref),
        normalization_notes=audit.notes,
        scrubber_counts=[
            ScrubberCount(rule_id=rule_id, count=count)
            for rule_id, count in sorted(audit.scrubber_counts.items())
        ],
        oversized=audit.oversized,
    )


def _event_signature(
    *,
    kind: EventKind,
    actor: str | None,
    call_id: str | None,
    name: str | None,
    status: CanonicalEventStatus,
    content: JsonValue,
    policy: CanonicalizationPolicy,
) -> str:
    payload: dict[str, object] = {
        "actor": actor,
        "content": content,
        "kind": kind,
        "name": name,
        "status": status,
    }
    if policy.tool_call_id_stability == "stable":
        payload["call_id"] = call_id
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _normalize_value(  # noqa: PLR0911
    value: object,
    *,
    path: str,
    scope: ScrubberScope,
    policy: CanonicalizationPolicy,
    audit: _NormalizationAudit,
) -> object:
    if isinstance(value, bytes | bytearray | memoryview):
        raw_bytes = bytes(value)
        audit.notes.append(f"binary_metadata:{path}")
        return {
            "$binary": {
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "size": len(raw_bytes),
                "type": type(value).__name__,
            }
        }
    if isinstance(value, str):
        parsed = _try_parse_json(value)
        if parsed is not _NOT_JSON:
            audit.notes.append(f"parsed_json_string:{path}")
            return _normalize_value(
                parsed,
                path=path,
                scope=scope,
                policy=policy,
                audit=audit,
            )
        normalized_text = _normalize_text(value, policy)
        normalized_text = _apply_scrubbers(
            normalized_text,
            scope=scope,
            policy=policy,
            audit=audit,
        )
        if len(normalized_text) > policy.max_content_chars:
            audit.oversized = True
            audit.notes.append(f"oversized:{path}")
            return {
                "$oversized": {
                    "head": normalized_text[:128],
                    "length": len(normalized_text),
                    "sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
                    "tail": normalized_text[-128:],
                }
            }
        return normalized_text
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        items = (
            sorted(value.items(), key=lambda item: str(item[0]))
            if policy.sort_object_keys
            else value.items()
        )
        for raw_key, item in items:
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if _path_is_ignored(child_path, key, policy):
                audit.ignored_fields += 1
                audit.notes.append(f"ignored:{child_path}")
                continue
            result[key] = _normalize_value(
                item,
                path=child_path,
                scope=scope,
                policy=policy,
                audit=audit,
            )
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            _normalize_value(
                item,
                path=f"{path}[{index}]",
                scope=scope,
                policy=policy,
                audit=audit,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical event content cannot contain NaN or Infinity")
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def _normalize_text(value: str, policy: CanonicalizationPolicy) -> str:
    result = (
        value.replace("\r\n", "\n").replace("\r", "\n") if policy.normalize_line_endings else value
    )
    if not policy.normalize_whitespace:
        return result
    pieces = result.split("```")
    for index in range(0, len(pieces), 2):
        pieces[index] = "\n".join(
            _WHITESPACE_RE.sub(" ", line) for line in pieces[index].split("\n")
        )
    return "```".join(pieces)


def _apply_scrubbers(
    value: str,
    *,
    scope: ScrubberScope,
    policy: CanonicalizationPolicy,
    audit: _NormalizationAudit,
) -> str:
    remaining = policy.string_scrubbers.max_replacements_per_leaf
    result = value
    if policy.string_scrubbers.preset == "volatile-runtime/v1":
        for preset_rule in _VOLATILE_PRESET:
            if remaining <= 0:
                break
            result, count = preset_rule.pattern.subn(
                preset_rule.replacement, result, count=remaining
            )
            if count:
                audit.scrubber_counts[preset_rule.id] += count
                audit.notes.append(f"scrubbed:{preset_rule.id}:{count}")
                remaining -= count
    for custom_rule in policy.string_scrubbers.rules:
        if remaining <= 0:
            break
        if custom_rule.scope not in ("all", scope):
            continue
        compiled = re.compile(custom_rule.pattern, _regex_flags(custom_rule))
        result, count = compiled.subn(custom_rule.replacement, result, count=remaining)
        if count:
            audit.scrubber_counts[custom_rule.id] += count
            audit.notes.append(f"scrubbed:{custom_rule.id}:{count}")
            remaining -= count
    if remaining == 0:
        audit.notes.append("scrubber_replacement_limit_reached")
    return result


def _regex_flags(rule: StringScrubberRule) -> int:
    flags = 0
    if "ignore_case" in rule.flags:
        flags |= re.IGNORECASE
    if "multiline" in rule.flags:
        flags |= re.MULTILINE
    if "dotall" in rule.flags:
        flags |= re.DOTALL
    return flags


def _path_is_ignored(path: str, key: str, policy: CanonicalizationPolicy) -> bool:
    if path in policy.ignored_json_paths:
        return True
    for pattern in policy.ignored_key_patterns:
        if pattern == r"(?i).*nonce$":
            if key.casefold().endswith("nonce"):
                return True
            continue
        if re.fullmatch(pattern, key):
            return True
    return False


def _message_kind(message: CanonicalMessage) -> EventKind:
    explicit = (message.kind or "").casefold()
    role = (message.role or "").casefold()
    if explicit in {"tool_call", "tool-call", "function_call"}:
        return "tool_call"
    if explicit in {"tool_result", "tool-result", "function_result"} or role in {
        "tool",
        "function",
    }:
        return "tool_result"
    if explicit in {"system", "user", "assistant"}:
        return cast("EventKind", explicit)
    if role in {"system", "user", "assistant"}:
        return cast("EventKind", role)
    return "other"


def _tool_calls(value: JsonValue | None) -> list[Mapping[str, object]]:
    parsed = _parse_json_string(value)
    if isinstance(parsed, Mapping):
        return [cast("Mapping[str, object]", parsed)]
    if not isinstance(parsed, list):
        return []
    return [cast("Mapping[str, object]", item) for item in parsed if isinstance(item, Mapping)]


def _parse_json_string(value: object) -> object:
    parsed = _try_parse_json(value) if isinstance(value, str) else _NOT_JSON
    return parsed if parsed is not _NOT_JSON else value


def _try_parse_json(value: str) -> object:
    stripped = value.strip()
    if not stripped or stripped[0] not in '[{"-0123456789tfn':
        return _NOT_JSON
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return _NOT_JSON
    return parsed


def _parse_timestamp(value: str | None, audit: _NormalizationAudit) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        audit.notes.append("invalid_timestamp")
        return None


def _source_ref_text(source_ref: SourceRef) -> str:
    suffix = f"/{source_ref.json_path}" if source_ref.json_path else ""
    return f"query:{source_ref.query_id}/row:{source_ref.row_identity}{suffix}"


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _has_visible_content(value: JsonValue) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None


def _text_content(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _character_ngrams(value: str, width: int) -> set[str]:
    if len(value) < width:
        return {value} if value else set()
    return {value[index : index + width] for index in range(len(value) - width + 1)}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
