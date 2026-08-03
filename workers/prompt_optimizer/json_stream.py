from __future__ import annotations

import json
import re


class IncrementalJsonExtractionError(ValueError):
    pass


def _safe_json_string_prefix(raw: str) -> str:
    index = 0
    safe_end = 0
    while index < len(raw):
        if raw[index] != "\\":
            safe_end = index + 1
            index += 1
            continue
        if index + 1 >= len(raw):
            break
        escape = raw[index + 1]
        if escape == "u":
            if index + 6 > len(raw):
                break
            digits = raw[index + 2 : index + 6]
            if not all(char in "0123456789abcdefABCDEF" for char in digits):
                raise IncrementalJsonExtractionError("invalid_unicode_escape")
            safe_end = index + 6
            index += 6
            continue
        if escape not in '\"\\/bfnrt':
            raise IncrementalJsonExtractionError("invalid_json_escape")
        safe_end = index + 2
        index += 2
    return raw[:safe_end]


def _raw_string_prefix(document: str, start: int) -> str:
    escaped = False
    chars: list[str] = []
    for char in document[start:]:
        if char == '"' and not escaped:
            break
        chars.append(char)
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    return "".join(chars)


class OptimizedFieldsJsonExtractor:
    def __init__(self, fields: tuple[str, ...]) -> None:
        self.fields = fields
        self.document = ""
        self.values = {field: "" for field in fields}

    def feed(self, chunk: str) -> dict[str, str]:
        self.document += chunk
        if len(self.document) > 32768:
            raise IncrementalJsonExtractionError("stream_json_too_large")
        marker = re.search(r'"optimized_fields"\s*:\s*\{', self.document)
        if marker is None:
            return {}
        tail = self.document[marker.end() :]
        deltas: dict[str, str] = {}
        for field in self.fields:
            field_marker = re.search(
                rf'"{re.escape(field)}"\s*:\s*"',
                tail,
            )
            if field_marker is None:
                continue
            raw = _raw_string_prefix(tail, field_marker.end())
            safe_raw = _safe_json_string_prefix(raw)
            try:
                decoded = json.loads(f'"{safe_raw}"')
            except json.JSONDecodeError as exc:
                raise IncrementalJsonExtractionError("invalid_json_string") from exc
            previous = self.values[field]
            if not decoded.startswith(previous):
                raise IncrementalJsonExtractionError("stream_value_rewritten")
            delta = decoded[len(previous) :]
            if delta:
                self.values[field] = decoded
                deltas[field] = delta
        return deltas

    def verify(self, parsed: dict) -> None:
        optimized = parsed.get("optimized_fields")
        if not isinstance(optimized, dict):
            raise IncrementalJsonExtractionError("optimized_fields_missing")
        for field in self.fields:
            if optimized.get(field) != self.values[field]:
                raise IncrementalJsonExtractionError("stream_final_mismatch")
