from __future__ import annotations

import json
import re
from typing import Any


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    values: list[str] = []
    if isinstance(content.get("text"), str) and content["text"].strip():
        values.append(content["text"].strip())
    for part in parts:
        if isinstance(part, str):
            value = part.strip()
            if value:
                values.append(value)
        elif isinstance(part, dict):
            nested = part.get("text") or part.get("content") or ""
            if isinstance(nested, str) and nested.strip():
                values.append(nested.strip())
    return "\n".join(values)


def conversation_turns(conversation: dict[str, Any]) -> list[dict[str, str]]:
    """Full ChatGPT thread: user + assistant, in time order."""
    rows: list[tuple[float, int, str, str]] = []
    for index, node in enumerate((conversation.get("mapping") or {}).values()):
        message = node.get("message") or {}
        role = (message.get("author") or {}).get("role") or ""
        if role not in {"user", "assistant"}:
            continue
        metadata = message.get("metadata") or {}
        if metadata.get("is_visually_hidden_from_conversation"):
            continue
        text = message_text(message)
        if not text:
            continue
        created = message.get("create_time")
        try:
            timestamp = float(created or 0)
        except (TypeError, ValueError):
            timestamp = 0
        rows.append((timestamp, index, role, text))
    rows.sort(key=lambda item: (item[0], item[1]))
    return [{"role": role, "content": text} for _, _, role, text in rows]


def format_transcript(turns: list[dict[str, str]], *, max_chars: int = 1_000_000) -> str:
    blocks: list[str] = []
    used = 0
    for turn in turns:
        label = "USER" if turn["role"] == "user" else "ASSISTANT"
        block = f"{label}:\n{turn['content']}".strip()
        extra = len(block) + (2 if blocks else 0)
        if used + extra > max_chars:
            remaining = max_chars - used - 40
            if remaining > 200:
                blocks.append(block[:remaining].rstrip() + "\n\n[transcript truncated]")
            break
        blocks.append(block)
        used += extra
    return "\n\n".join(blocks)


def parse_transcript_turns(transcript: str) -> list[dict[str, str]]:
    """Parse USER:/ASSISTANT: export text back into chat turns."""
    text = (transcript or "").strip()
    if not text:
        return []
    if not re.match(r"^(USER|ASSISTANT):", text):
        return [{"role": "user", "content": text}]

    chunks = re.split(r"(?m)^(USER|ASSISTANT):\s*\n", text)
    turns: list[dict[str, str]] = []
    index = 1
    while index + 1 < len(chunks):
        label = chunks[index].strip().upper()
        body = (chunks[index + 1] or "").strip()
        role = "user" if label == "USER" else "assistant"
        if body:
            turns.append({"role": role, "content": body})
        index += 2
    return turns


def parse_json_array_best_effort(raw: bytes) -> list[Any]:
    """Parse a JSON array, keeping complete objects from a truncated file."""
    text = raw.decode("utf-8", "replace")
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    start = text.find("[")
    if start < 0:
        return []
    index = start + 1
    items: list[Any] = []
    length = len(text)
    while index < length:
        while index < length and text[index] in " \n\r\t,":
            index += 1
        if index >= length or text[index] == "]":
            break
        try:
            obj, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            items.append(obj)
        index = end
    return items
