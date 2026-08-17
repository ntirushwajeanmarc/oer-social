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


def zip_entry_basename(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1].lower()


def is_conversations_entry(name: str) -> bool:
    base = zip_entry_basename(name)
    return base.startswith("conversations") and base.endswith(".json")


def is_projects_entry(name: str) -> bool:
    base = zip_entry_basename(name)
    return base == "projects.json" or (
        base.startswith("projects-") and base.endswith(".json")
    )


def conversation_project_id(conversation: dict[str, Any]) -> str | None:
    """ChatGPT Project id: project_id, g-p- template, or snorlax gizmo."""
    raw = conversation.get("project_id")
    if raw:
        value = str(raw).strip()
        if value and value.lower() not in {"none", "null"}:
            return value

    gizmo_type = str(conversation.get("gizmo_type") or "").strip().lower()
    gizmo_id = str(conversation.get("gizmo_id") or "").strip()
    if gizmo_type in {"snorlax", "project"} and gizmo_id:
        return gizmo_id

    template = str(conversation.get("conversation_template_id") or "").strip()
    if template.startswith("g-p-"):
        return template
    if gizmo_id.startswith("g-p-"):
        return gizmo_id
    for node in (conversation.get("mapping") or {}).values():
        if not isinstance(node, dict):
            continue
        metadata = (node.get("message") or {}).get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        nested = str(
            metadata.get("project_id") or metadata.get("conversation_template_id") or ""
        ).strip()
        if nested.startswith("g-p-"):
            return nested
    return None


def conversation_project_hint_name(conversation: dict[str, Any]) -> str:
    for key in ("project_name", "gizmo_name", "gpt_name"):
        value = conversation.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return ""


def parse_projects_payload(raw: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        data = parse_json_array_best_effort(raw)
    if isinstance(data, dict):
        nested = data.get("projects") or data.get("items") or data.get("data")
        data = nested if nested is not None else [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def project_record(item: dict[str, Any]) -> tuple[str, str, str] | None:
    source_id = str(
        item.get("id") or item.get("project_id") or item.get("gizmo_id") or ""
    ).strip()
    if not source_id:
        return None
    name = str(item.get("name") or item.get("title") or "").strip() or (
        f"ChatGPT project {source_id[-12:]}"
    )
    instructions = str(
        item.get("custom_instructions")
        or item.get("instructions")
        or item.get("prompt")
        or item.get("system_prompt")
        or ""
    ).strip()
    description = str(item.get("description") or "").strip()
    files = item.get("file_manifest") or item.get("files") or []
    file_names: list[str] = []
    if isinstance(files, list):
        for file in files:
            if isinstance(file, str) and file.strip():
                file_names.append(file.strip())
            elif isinstance(file, dict):
                label = str(file.get("name") or file.get("filename") or "").strip()
                if label:
                    file_names.append(label)
    parts: list[str] = []
    if description:
        parts.append(description)
    if instructions:
        parts.append("Custom instructions:\n" + instructions)
    if file_names:
        parts.append(
            "Files in ChatGPT (names only; binaries are not in the export):\n"
            + "\n".join(f"- {name}" for name in file_names[:40])
        )
    return source_id, name[:200], "\n\n".join(parts)[:8000]


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
