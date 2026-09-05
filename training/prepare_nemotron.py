"""Prepare safe display overlays from NVIDIA Nemotron-Personas-USA.

Nemotron records are synthetic identity/context examples, not observed social
behavior. This preparation step removes sensitive demographics and free-form
biographies, rejects minors, requires high-confidence niche relevance, and
derives varied simulation priors rather than claiming behavioral labels.

Source: nvidia/Nemotron-Personas-USA (CC BY 4.0).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

PERSONA_PREP_VERSION = "nemotron-display-v2.0"

NICHES: dict[str, tuple[str, ...]] = {
    "tech": (
        "artificial intelligence",
        "machine learning",
        "software",
        "developer",
        "programmer",
        "data science",
        "cybersecurity",
        "cloud",
        "devops",
        "computer",
        "technology",
        "python",
        "javascript",
    ),
    "fitness": (
        "fitness",
        "personal trainer",
        "strength",
        "conditioning",
        "physical therapy",
        "physiotherapy",
        "exercise",
        "gym",
        "running",
        "yoga",
        "nutrition",
        "athlete",
        "athletic",
    ),
    "finance": (
        "finance",
        "financial",
        "accounting",
        "accountant",
        "bookkeeping",
        "banking",
        "investment",
        "investor",
        "trading",
        "trader",
        "economics",
        "economist",
        "audit",
        "tax",
        "budgeting",
    ),
    "comedy": (
        "comedy",
        "comedian",
        "stand-up",
        "standup",
        "improv",
        "humor",
        "humour",
        "comic",
        "satire",
        "sketch comedy",
    ),
}

NICHE_DEFAULT_INTERESTS: dict[str, tuple[str, ...]] = {
    "tech": ("software", "AI tools", "technology"),
    "fitness": ("exercise", "strength", "wellness"),
    "finance": ("personal finance", "markets", "financial education"),
    "comedy": ("comedy", "humor", "entertainment"),
}

_MINOR_TEXT = re.compile(
    r"\b(?:"
    r"(?:[0-9]|1[0-7])[- ]year[- ]old|"
    r"infant|baby|toddler|minor|child|children|"
    r"elementary school|middle school|high school student|"
    r"nursery rhymes?|playdates?|crawling"
    r")\b",
    re.IGNORECASE,
)
_UNUSABLE_OCCUPATIONS = {
    "",
    "unknown",
    "none",
    "not in workforce",
    "unemployed",
    "student",
}


def _parse_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(value).strip() for value in raw if str(value).strip()]
    text = str(raw or "").strip()
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(value).strip() for value in parsed if str(value).strip()]
        except (SyntaxError, ValueError):
            pass
    return [part.strip() for part in re.split(r"[,;]", text) if part.strip()][:12]


def _clamp(value: float) -> float:
    return round(max(0.05, min(0.95, value)), 3)


def _source_key(row: dict) -> str:
    return str(row.get("uuid") or row.get("source_uuid") or row.get("id") or "unknown")


def _source_id(row: dict) -> str:
    return hashlib.sha256(_source_key(row).encode("utf-8")).hexdigest()[:16]


def _stable_noise(row: dict, label: str, scale: float = 0.08) -> float:
    digest = hashlib.sha256(f"{_source_key(row)}:{label}".encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    return (2.0 * unit - 1.0) * scale


def _minor_reason(row: dict) -> str | None:
    for key in ("age", "age_years", "age_range"):
        value = row.get(key)
        if value is None:
            continue
        try:
            if float(value) < 18:
                return "minor_age"
        except (TypeError, ValueError):
            ages = [int(part) for part in re.findall(r"\d{1,3}", str(value))]
            if (ages and min(ages) < 18) or _MINOR_TEXT.search(str(value)):
                return "minor_age"
    text = " ".join(
        str(row.get(key) or "")
        for key in (
            "occupation",
            "persona",
            "professional_persona",
            "hobbies_and_interests",
        )
    )
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    return "minor_description" if _MINOR_TEXT.search(text) else None


def _phrase_hits(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def route_niche(occupation: str, hobbies: list[str], persona: str) -> str | None:
    """Route only high-confidence records; ties and weak matches are rejected."""

    occupation_text = str(occupation or "").lower()
    hobbies_text = " ".join(hobbies).lower()
    persona_text = str(persona or "").lower()
    identity_scores = {
        niche: 4 * _phrase_hits(occupation_text, terms)
        + _phrase_hits(persona_text, terms)
        for niche, terms in NICHES.items()
    }
    scores = {
        niche: identity_scores[niche] + 2 * _phrase_hits(hobbies_text, terms)
        for niche, terms in NICHES.items()
    }
    best_score = max(scores.values(), default=0)
    winners = [niche for niche, score in scores.items() if score == best_score]
    return (
        winners[0]
        if best_score >= 1
        and len(winners) == 1
        and identity_scores[winners[0]] > 0
        else None
    )


def _safe_interests(row: dict, niche: str) -> list[str]:
    candidates = _parse_list(
        row.get("skills_and_expertise_list") or row.get("skills_and_expertise")
    )
    candidates += _parse_list(
        row.get("hobbies_and_interests_list") or row.get("hobbies_and_interests")
    )
    safe: list[str] = []
    for candidate in candidates:
        value = re.sub(r"\s+", " ", candidate).strip()[:60]
        if not value or _MINOR_TEXT.search(value):
            continue
        if _phrase_hits(value, NICHES[niche]) and value.lower() not in {
            existing.lower() for existing in safe
        }:
            safe.append(value)
        if len(safe) >= 6:
            break
    return safe or list(NICHE_DEFAULT_INTERESTS[niche])


def _behavior_priors(row: dict, niche: str, interests: list[str]) -> dict[str, float]:
    """Create correlated simulation priors from non-sensitive professional context."""

    occupation = str(row.get("occupation") or "")
    education = str(row.get("education_level") or "")
    source_text = f"{occupation} {' '.join(interests)}".lower()

    analytical = _phrase_hits(
        source_text,
        ("research", "analysis", "science", "engineer", "audit", "data", "technical"),
    )
    social = _phrase_hits(
        source_text,
        ("coach", "community", "teacher", "creator", "writer", "perform", "manager"),
    )
    creative = _phrase_hits(
        source_text,
        ("comedy", "improv", "design", "art", "writer", "creator", "perform"),
    )
    commercial = _phrase_hits(
        source_text,
        ("sales", "marketing", "founder", "business", "trader", "entrepreneur"),
    )
    advanced_education = any(
        marker in education.lower()
        for marker in ("bachelor", "master", "doctor", "professional")
    )

    expertise = _clamp(0.42 + 0.18 * advanced_education + 0.045 * min(3, analytical))
    activity = _clamp(0.43 + 0.055 * min(3, social) + _stable_noise(row, "activity"))
    novelty = _clamp(
        0.42
        + 0.055 * min(3, creative)
        + (0.04 if niche == "tech" else 0.0)
        + _stable_noise(row, "novelty")
    )
    promo = _clamp(
        0.24
        + 0.065 * min(3, commercial)
        - 0.035 * min(3, analytical)
        + _stable_noise(row, "promo", 0.05)
    )
    evidence = _clamp(
        0.36
        + 0.09 * min(3, analytical)
        + 0.08 * expertise
        + _stable_noise(row, "evidence", 0.05)
    )
    reply = _clamp(
        0.06
        + 0.15 * activity
        + 0.025 * min(3, social)
        + _stable_noise(row, "reply", 0.035)
    )
    repost = _clamp(
        0.07 + 0.14 * activity + 0.08 * novelty + _stable_noise(row, "repost", 0.04)
    )
    quote = _clamp(
        0.035 + 0.1 * activity + 0.06 * evidence + _stable_noise(row, "quote", 0.03)
    )
    share = _clamp(
        0.07
        + 0.13 * activity
        + 0.035 * min(3, social)
        + _stable_noise(row, "share", 0.035)
    )
    click = _clamp(
        0.19 + 0.19 * novelty + 0.13 * evidence + _stable_noise(row, "click", 0.05)
    )
    follow = _clamp(
        0.015
        + 0.065 * activity
        + 0.025 * novelty
        + _stable_noise(row, "follow", 0.015)
    )
    dwell = _clamp(
        0.28 + 0.17 * evidence + 0.11 * novelty + _stable_noise(row, "dwell", 0.05)
    )
    negative = _clamp(
        0.13
        + 0.2 * evidence
        + 0.16 * (1.0 - promo)
        + _stable_noise(row, "negative", 0.04)
    )
    return {
        "expertise": expertise,
        "activity_level": activity,
        "novelty_seeking": novelty,
        "promotional_tolerance": promo,
        "reply_tendency": reply,
        "repost_tendency": repost,
        "quote_tendency": quote,
        "share_tendency": share,
        "click_tendency": click,
        "follow_tendency": follow,
        "dwell_tendency": dwell,
        "negative_sensitivity": negative,
        "evidence_demand": evidence,
    }


def to_persona(row: dict, niche: str, index: int) -> dict | None:
    """Convert a safe adult source row to a generic display overlay."""

    if niche not in NICHES or _minor_reason(row):
        return None
    occupation = re.sub(r"\s+", " ", str(row.get("occupation") or "")).strip()
    if occupation.lower() in _UNUSABLE_OCCUPATIONS:
        return None
    identity_text = " ".join(
        (
            occupation,
            str(row.get("professional_persona") or row.get("persona") or ""),
        )
    )
    if not _phrase_hits(identity_text, NICHES[niche]):
        return None

    interests = _safe_interests(row, niche)
    slug = re.sub(r"[^a-z0-9]+", "_", occupation.lower()).strip("_")[:24]
    source_id = _source_id(row)
    result: dict[str, object] = {
        "id": f"{slug or niche}_{index}_{source_id[:6]}",
        "name": occupation.title()[:60],
        "role": f"{occupation.title()} interested in {niche} content"[:100],
        "interests": interests,
        "source": "nvidia/Nemotron-Personas-USA",
        "source_id": source_id,
        "source_version": PERSONA_PREP_VERSION,
        "behavior_semantics": "derived_simulation_prior_not_observed_label",
    }
    result.update(_behavior_priors(row, niche, interests))
    return result


def prepare(per_niche: int, max_scan: int, out_dir: Path, seed: int) -> dict:
    if per_niche <= 0 or max_scan <= 0:
        raise ValueError("per_niche and max_scan must be positive")

    # Keep the heavy optional dependency outside module import so helper tests and
    # static validation work in the application environment.
    from datasets import load_dataset

    dataset = load_dataset("nvidia/Nemotron-Personas-USA", split="train", streaming=True)
    dataset = dataset.shuffle(seed=seed, buffer_size=5_000)
    buckets: dict[str, list[dict]] = defaultdict(list)
    rejection_counts: dict[str, int] = defaultdict(int)
    scanned = 0
    for row in dataset:
        scanned += 1
        if _minor_reason(row):
            rejection_counts["minor"] += 1
            continue
        occupation = str(row.get("occupation") or "")
        hobbies = _parse_list(
            row.get("hobbies_and_interests_list") or row.get("hobbies_and_interests")
        )
        persona_text = str(row.get("professional_persona") or row.get("persona") or "")
        niche = route_niche(occupation, hobbies, persona_text)
        if niche is None:
            rejection_counts["no_high_confidence_niche"] += 1
        elif len(buckets[niche]) < per_niche:
            persona = to_persona(row, niche, len(buckets[niche]) + 1)
            if persona is None:
                rejection_counts["unsafe_or_unusable"] += 1
            else:
                buckets[niche].append(persona)
        if all(len(buckets[niche_name]) >= per_niche for niche_name in NICHES):
            break
        if scanned >= max_scan:
            break

    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    for niche in NICHES:
        personas = buckets[niche]
        path = out_dir / f"{niche}_nemotron.json"
        payload = {
            "niche": niche,
            "source": "nvidia/Nemotron-Personas-USA",
            "license": "CC BY 4.0",
            "version": PERSONA_PREP_VERSION,
            "seed": seed,
            "behavior_semantics": "derived_simulation_prior_not_observed_label",
            "personas": personas,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written[niche] = len(personas)

    summary = {
        "version": PERSONA_PREP_VERSION,
        "seed": seed,
        "scanned": scanned,
        "written": written,
        "rejections": dict(sorted(rejection_counts.items())),
        "out": str(out_dir),
    }
    (out_dir / "nemotron_prepare_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-niche", type=int, default=24)
    parser.add_argument("--max-scan", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/processed/nemotron_packs")
    args = parser.parse_args()
    print(json.dumps(prepare(args.per_niche, args.max_scan, Path(args.out), args.seed), indent=2))


if __name__ == "__main__":
    main()
