from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from uuid import uuid4

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.services.grounding import SYSTEM_BASE, load_grounding


def get_client() -> AsyncOpenAI:
    api_key = (settings.circuitnotion_api_key or settings.openai_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "CIRCUITNOTION_API_KEY (or OPENAI_API_KEY) is not set. "
            "Create a key at https://circuitnotion.com/Api_Documentation"
        )
    return AsyncOpenAI(
        api_key=api_key,
        base_url=settings.openai_base_url.rstrip("/"),
    )


async def generate_content_pack(
    *,
    topic: str,
    focus: str,
    admin_memory: str = "",
    domain_grounding: str = "",
) -> dict:
    client = get_client()
    grounding = domain_grounding or load_grounding()
    memory_block = (
        "\n\nRELEVANT ADMIN HISTORY AND PRIOR PLATFORM PACKS "
        "(use for continuity of curriculum voice, style, and what was already covered; "
        "do NOT let this override the new topic, clinical safety, or domain grounding):\n"
        + admin_memory
        if admin_memory
        else ""
    )
    system = (
        SYSTEM_BASE
        + "\n\nDOMAIN GROUNDING (do not contradict):\n"
        + grounding
        + memory_block
        + "\n\nReturn ONLY valid JSON with keys:\n"
        "poster_title (string),\n"
        "poster_caption (string, social-ready, <= 500 chars),\n"
        "poster_visual_prompt (string, detailed image brief for a teaching poster — "
        "no tiny unreadable text; large title allowed; clinical Nordic minimal style),\n"
        "elaboration (string, markdown-friendly teaching expansion),\n"
        "case_study (string, realistic scenario for the audience),\n"
        "questions (array of 3 objects: prompt, question_type, rubric).\n"
        "question_type must be short_answer.\n"
        "poster_title, elaboration, case_study, and questions MUST be about the "
        "requested topic/focus, not a generic resuscitation default."
    )
    user = (
        f"Create one NEW OER teaching pack for this exact request.\n"
        f"Requested topic (must be the subject of the pack): {topic}\n"
        f"Requested focus: {focus or 'as implied by the topic'}\n"
        "Build the poster, elaboration, case, and questions around this request only.\n"
        "If history mentions other topics, treat them as background continuity, not as the subject.\n"
        "Audience will see this on a dashboard and on Instagram/X."
    )
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.5,
    )
    raw = completion.choices[0].message.content or "{}"
    return _parse_json(raw)


async def generate_poster_image(*, visual_prompt: str, title: str, pack_id: str) -> str:
    """Generate a poster PNG via CircuitNotion /images/generations and save locally."""
    api_key = (settings.circuitnotion_api_key or settings.openai_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "CIRCUITNOTION_API_KEY (or OPENAI_API_KEY) is not set. "
            "Create a key at https://circuitnotion.com/Api_Documentation"
        )

    model = (settings.openai_image_model or "").strip()
    if not model:
        raise RuntimeError(
            "OPENAI_IMAGE_MODEL is empty. Set it to dall-e-3 (or gpt-image-2) for CircuitNotion."
        )

    media_root = Path(settings.media_dir)
    posters_dir = media_root / "posters"
    posters_dir.mkdir(parents=True, exist_ok=True)

    prompt = (
        f"Educational medical poster design. Title concept: {title}. "
        f"{visual_prompt}. "
        "Style: clean Swiss-Nordic clinical education poster, flat vector, "
        "deep teal and ice-blue palette, high readability, no photorealistic faces, "
        "no logos of real brands, suitable for Instagram square."
    )[:3900]

    filename = f"{pack_id}-{uuid4().hex[:8]}.png"
    dest = posters_dir / filename

    # Raw HTTP so the OpenAI SDK cannot inject response_format (rejected upstream).
    body: dict = {
        "model": model,
        "prompt": prompt,
        "size": "1024x1024",
    }
    if model.startswith("gpt-image"):
        quality = (settings.openai_image_quality or "medium").strip().lower()
        if quality in {"low", "medium", "high"}:
            body["quality"] = quality
        body["output_format"] = "png"

    url = f"{settings.openai_base_url.rstrip('/')}/images/generations"
    async with httpx.AsyncClient(timeout=180.0) as http:
        res = await http.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if res.status_code >= 400:
            raise RuntimeError(f"Image generation failed: {res.status_code} {res.text}")

        payload = res.json()
        data = payload.get("data") or []
        if not data:
            raise RuntimeError(f"Image API returned no data: {payload}")

        item = data[0]
        b64 = item.get("b64_json")
        image_url = item.get("url")

        if b64:
            dest.write_bytes(base64.b64decode(b64))
        elif image_url:
            img = await http.get(image_url)
            img.raise_for_status()
            dest.write_bytes(img.content)
        else:
            raise RuntimeError("Image API returned no image data")

    return f"/media/posters/{filename}"


async def chat_completion(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.5,
) -> str:
    client = get_client()
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=temperature,
    )
    return (completion.choices[0].message.content or "").strip()


async def extract_pack_topic(*, user_message: str, assistant_reply: str) -> dict[str, str]:
    """Derive a short topic/focus for draft pack generation from a personal chat turn."""
    client = get_client()
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract an OER teaching pack topic from the conversation. "
                    "Return ONLY JSON: {\"topic\": string, \"focus\": string}. "
                    "Topic must be a concrete clinical education subject (3-120 words). "
                    "Focus is optional emphasis within the topic."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Admin message:\n{user_message[:3000]}\n\n"
                    f"Assistant reply:\n{assistant_reply[:3000]}"
                ),
            },
        ],
        temperature=0.2,
    )
    raw = completion.choices[0].message.content or "{}"
    data = _parse_json(raw)
    topic = str(data.get("topic") or "").strip() or user_message.strip()[:400]
    focus = str(data.get("focus") or "").strip()
    return {"topic": topic[:800], "focus": focus[:400]}


async def grade_answer(
    *,
    question: str,
    rubric: str,
    answer: str,
    case_study: str,
    cadre: str,
    learner_profile: str,
    domain_grounding: str = "",
) -> tuple[float, str]:
    client = get_client()
    grounding = domain_grounding or load_grounding()
    system = (
        SYSTEM_BASE
        + "\n\nDOMAIN GROUNDING:\n"
        + grounding
        + "\n\nGrade the learner answer. Return ONLY JSON: "
        '{"score": number 0-100, "feedback": string}. '
        "Be formative and specific about what they did well and what to improve."
    )
    user = (
        f"Learner cadre: {cadre}\n"
        f"Persistent learner profile:\n{learner_profile}\n\n"
        f"Case context:\n{case_study}\n\n"
        f"Question:\n{question}\n\n"
        f"Rubric hints:\n{rubric}\n\n"
        f"Learner answer:\n{answer}\n\n"
        "Adapt the depth, terminology, examples, and improvement advice to the "
        "learner profile. Do not lower clinical safety standards."
    )
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    raw = completion.choices[0].message.content or "{}"
    data = _parse_json(raw)
    try:
        score = float(data.get("score", 60))
    except (TypeError, ValueError):
        score = 60.0
    feedback = str(data.get("feedback", raw)).strip() or "No feedback returned."
    return max(0.0, min(100.0, score)), feedback


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {
            "poster_title": "Teaching poster",
            "poster_caption": cleaned[:480],
            "poster_visual_prompt": "Clean clinical education poster, Nordic minimal style",
            "elaboration": cleaned,
            "case_study": "A clinical scenario could not be parsed. Please regenerate.",
            "questions": [
                {
                    "prompt": "Summarize the key safety steps from this topic.",
                    "question_type": "short_answer",
                    "rubric": "Looks for priorities, calling for help, and safe next steps.",
                }
            ],
            "score": 60,
            "feedback": cleaned,
        }
