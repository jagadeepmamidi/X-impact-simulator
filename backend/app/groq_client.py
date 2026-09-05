from __future__ import annotations

import json
import re
from typing import Any

try:
    from groq import APIError, Groq
except ImportError:  # The deterministic simulator remains usable without the optional SDK.
    Groq = None  # type: ignore[assignment]

    class APIError(Exception):
        pass

from app.config import settings
from app.schemas import ContentFeatures, Persona, PersonaReaction, Explanation
from app.scoring import clamp01

CONTENT_SCHEMA = """Respond in JSON with keys:
topics (string[]), format (educational|opinion|promo|meme|news|other),
sentiment (positive|neutral|negative), hook_strength, clarity, novelty,
controversy, promotional_intensity, safety_risk, visual_hook
(all floats 0-1), transcript_excerpt (string)."""


def _client() -> Any | None:
    if not settings.groq_enabled or Groq is None:
        return None
    try:
        return Groq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout_seconds,
            max_retries=settings.groq_max_retries,
        )
    except Exception:
        return None


def heuristic_content(text: str, media_note: str) -> ContentFeatures:
    t = text.lower()
    words = re.findall(r"[a-z0-9#]+", t)
    promo_hits = sum(w in {"buy", "link", "subscribe", "follow", "discount", "sale", "promo"} for w in words)
    first = text.strip().split("\n")[0] if text.strip() else ""
    hook = clamp01(0.35 + min(len(first), 80) / 160 + (0.2 if first.endswith("?") else 0))
    return ContentFeatures(
        topics=list(dict.fromkeys(words[:8])),
        format="promo" if promo_hits else "opinion" if "i " in t else "educational",
        sentiment="negative" if any(w in t for w in ("hate", "scam", "awful")) else "positive",
        hook_strength=round(hook, 3),
        clarity=round(clamp01(0.85 - abs(len(text) - 180) / 800), 3),
        novelty=round(clamp01(0.4 + 0.002 * len(set(words))), 3),
        controversy=round(clamp01(0.08 * t.count("!") + 0.2 * ("vs" in t)), 3),
        promotional_intensity=round(clamp01(0.15 * promo_hits), 3),
        safety_risk=0.02,
        visual_hook=0.0,
        transcript_excerpt=text[:400],
        source="heuristic",
        media_note=media_note,
    )


def _parse_content(raw: str, media_note: str) -> ContentFeatures:
    data = json.loads(raw)
    return ContentFeatures(
        topics=list(data.get("topics") or []),
        format=str(data.get("format") or "other"),
        sentiment=str(data.get("sentiment") or "neutral"),
        hook_strength=clamp01(float(data.get("hook_strength", 0.5))),
        clarity=clamp01(float(data.get("clarity", 0.5))),
        novelty=clamp01(float(data.get("novelty", 0.5))),
        controversy=clamp01(float(data.get("controversy", 0.2))),
        promotional_intensity=clamp01(float(data.get("promotional_intensity", 0.2))),
        safety_risk=clamp01(float(data.get("safety_risk", 0.05))),
        visual_hook=clamp01(float(data.get("visual_hook", 0.0))),
        transcript_excerpt=str(data.get("transcript_excerpt") or "")[:500],
        source="groq",
        media_note=media_note,
    )


def groq_text_content(text: str, media_note: str) -> ContentFeatures | None:
    client = _client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=settings.groq_text_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You extract social post features. " + CONTENT_SCHEMA},
                {"role": "user", "content": text[:6000]},
            ],
            temperature=0.2,
        )
        return _parse_content(response.choices[0].message.content or "{}", media_note)
    except (APIError, json.JSONDecodeError, TypeError, ValueError):
        return None


def groq_vision_content(
    text: str,
    image_data_urls: list[str],
    media_note: str,
) -> ContentFeatures | None:
    client = _client()
    if client is None or not image_data_urls:
        return None
    parts: list[dict[str, Any]] = [{"type": "text", "text": (text or "Analyze these frames.")[:3000] + "\n" + CONTENT_SCHEMA}]
    for url in image_data_urls[:5]:
        parts.append({"type": "image_url", "image_url": {"url": url}})
    try:
        response = client.chat.completions.create(
            model=settings.groq_vision_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": parts}],
            temperature=0.2,
        )
        return _parse_content(response.choices[0].message.content or "{}", media_note)
    except (APIError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _prob(item: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in item and item[key] is not None:
            return clamp01(float(item[key]))
    return clamp01(default)


def _reaction_from_item(item: dict, pid: str) -> PersonaReaction:
    like = _prob(item, "like_probability", "favorite", "favorite_score", default=0.3)
    reply = _prob(item, "reply_probability", "reply", "reply_score", default=0.1)
    repost = _prob(item, "repost_probability", "retweet", "retweet_score", default=0.1)
    dwell = _prob(item, "dwell_probability", "dwell", "dwell_score", default=0.4)
    follow = _prob(item, "follow_probability", "follow_author", "follow_author_score", default=0.05)
    quote = _prob(item, "quote_probability", "quote", "quote_score", default=round(reply * 0.35, 3))
    share = _prob(item, "share_probability", "share", "share_score", default=round(repost * 0.4, 3))
    share_dm = _prob(item, "share_via_dm_probability", "share_via_dm", default=round(share * 0.25, 3))
    share_copy = _prob(
        item, "share_via_copy_link_probability", "share_via_copy_link", default=round(share * 0.12, 3)
    )
    click = _prob(item, "click_probability", "click", "click_score", default=dwell)
    negative = _prob(item, "negative_feedback_probability", default=0.05)
    not_interested = _prob(item, "not_interested_probability", "not_interested", default=round(negative * 0.5, 3))
    mute = _prob(item, "mute_probability", "mute", default=round(negative * 0.22, 3))
    block = _prob(item, "block_probability", "block", default=round(negative * 0.16, 3))
    report = _prob(item, "report_probability", "report", default=round(negative * 0.08, 3))
    component_union = 1.0 - (
        (1.0 - not_interested) * (1.0 - mute) * (1.0 - block) * (1.0 - report)
    )
    lumped = max(negative, component_union)
    dwell_time = float(item.get("dwell_time") or dwell * 10.0)
    return PersonaReaction(
        persona_id=pid,
        topic_affinity=_prob(item, "topic_affinity", default=0.5),
        like_probability=like,
        reply_probability=reply,
        repost_probability=repost,
        quote_probability=quote,
        share_probability=share,
        share_via_dm_probability=share_dm,
        share_via_copy_link_probability=share_copy,
        dwell_probability=dwell,
        dwell_time=max(0.0, min(120.0, dwell_time)),
        click_probability=click,
        photo_expand_probability=_prob(item, "photo_expand_probability", "photo_expand", default=0.0),
        video_open_probability=_prob(item, "video_open_probability", "video_open", default=0.0),
        open_link_probability=_prob(item, "open_link_probability", "open_link", default=0.0),
        quoted_click_probability=_prob(item, "quoted_click_probability", "quoted_click", default=round(quote * click, 3)),
        follow_probability=follow,
        post_unexplored_probability=_prob(item, "post_unexplored_probability", "post_unexplored", default=0.0),
        not_interested_probability=not_interested,
        mute_probability=mute,
        block_probability=block,
        report_probability=report,
        not_dwelled_probability=_prob(
            item, "not_dwelled_probability", "not_dwelled", default=round(max(0.0, 1.0 - dwell) * 0.45, 3)
        ),
        negative_feedback_probability=clamp01(lumped),
        reason=str(item.get("reason") or "No reason supplied.")[:280],
    )


def groq_transcribe(audio_path: str) -> str:
    client = _client()
    if client is None:
        return ""
    try:
        with open(audio_path, "rb") as handle:
            result = client.audio.transcriptions.create(
                model=settings.groq_whisper_model,
                file=handle,
                response_format="text",
            )
        return str(result).strip()
    except (APIError, OSError, TypeError, ValueError):
        return ""


def groq_persona_reactions(
    personas: list[Persona],
    content: ContentFeatures,
) -> list[PersonaReaction] | None:
    client = _client()
    if client is None:
        return None
    payload = {
        "content": content.model_dump(),
        "personas": [p.model_dump() for p in personas],
    }
    try:
        response = client.chat.completions.create(
            model=settings.groq_text_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return JSON {\"reactions\": [...]} for each persona. "
                        "Each probability is a 0-1 AFFINITY (how strongly this archetype "
                        "would engage if shown the post), NOT an impression-level rate "
                        "and NOT a feed-wide percentage. Python maps affinities onto "
                        "base rates. Use the full 0-1 range: off-niche personas near 0.05-0.25, "
                        "strong fit 0.55-0.85, almost nobody at 0.95. "
                        "Copy-link, report, block, and follow affinities must stay low "
                        "unless the post clearly invites that action. "
                        "Fields: persona_id, topic_affinity, like_probability (favorite), "
                        "reply_probability, repost_probability (retweet), quote_probability, "
                        "share_probability, share_via_dm_probability, "
                        "share_via_copy_link_probability (rare, usually << share), "
                        "dwell_probability, dwell_time (seconds, typically 0-20), "
                        "click_probability, photo_expand_probability, video_open_probability, "
                        "open_link_probability, quoted_click_probability, follow_probability, "
                        "post_unexplored_probability, not_interested_probability, "
                        "mute_probability, block_probability, report_probability, "
                        "not_dwelled_probability (all 0-1 except dwell_time), reason. "
                        "Do not output an overall score or impact_score."
                    ),
                },
                {"role": "user", "content": json.dumps(payload)[:20000]},
            ],
            temperature=0.3,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except (APIError, json.JSONDecodeError, TypeError, ValueError):
        return None
    items = data.get("reactions") or data.get("personas") or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return None
    expected_ids = [persona.id for persona in personas]
    returned_ids = [str(item.get("persona_id") or "") for item in items]
    # Partial, duplicate, or unknown persona responses would silently bias the
    # audience. Reject the whole response and use the deterministic fallback.
    if len(returned_ids) != len(expected_ids) or len(set(returned_ids)) != len(returned_ids):
        return None
    if set(returned_ids) != set(expected_ids):
        return None
    by_id = {str(item["persona_id"]): item for item in items}
    try:
        return [_reaction_from_item(by_id[pid], pid) for pid in expected_ids]
    except (TypeError, ValueError, KeyError):
        return None


def groq_explain(report: dict) -> Explanation | None:
    client = _client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=settings.groq_text_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You explain an uncalibrated simulation. JSON keys: "
                        "headline, summary, suggestions (3 strings). "
                        "Never invent a new numeric impact score. Never claim virality. "
                        "Say comparative estimate, not prediction."
                    ),
                },
                {"role": "user", "content": json.dumps(report)[:18000]},
            ],
            temperature=0.4,
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except (APIError, json.JSONDecodeError, TypeError, ValueError):
        return None
    suggestions = data.get("suggestions") or []
    return Explanation(
        headline=str(data.get("headline") or "Simulation complete"),
        summary=str(data.get("summary") or ""),
        suggestions=[str(s) for s in suggestions][:5],
        source="groq",
    )
