"""Sample Nemotron-Personas-USA into simulator pack JSON.

Drops protected/targeting fields (sex, age, marital, zip). Routes by occupation/hobbies.
CC BY 4.0 — attribute NVIDIA Nemotron-Personas-USA.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

NICHES = {
    "tech": ("software", "engineer", "developer", "programmer", "data scientist", "machine learning", "it ", "computer"),
    "fitness": ("fitness", "coach", "trainer", "athletic", "physical therapist", "gym", "yoga"),
    "finance": ("account", "financ", "bank", "analyst", "trader", "auditor", "economist"),
    "comedy": ("comed", "entertain", "actor", "writer", "humor", "stand-up", "improv"),
}


def _parse_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    text = str(raw or "").strip()
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except (SyntaxError, ValueError):
            pass
    return [p.strip() for p in re.split(r"[,;]", text) if p.strip()][:8]


def _clamp(value: float) -> float:
    return round(max(0.05, min(0.95, value)), 2)


def route_niche(occupation: str, hobbies: list[str], persona: str) -> str | None:
    blob = f"{occupation} {' '.join(hobbies)} {persona}".lower()
    for niche, keys in NICHES.items():
        if any(k in blob for k in keys):
            return niche
    return None


def to_persona(row: dict, niche: str, index: int) -> dict:
    hobbies = _parse_list(row.get("hobbies_and_interests_list") or row.get("hobbies_and_interests"))
    skills = _parse_list(row.get("skills_and_expertise_list") or [])
    occupation = str(row.get("occupation") or "creator")
    interests = (hobbies + skills)[:6] or [occupation.replace("_", " ")]
    edu = str(row.get("education_level") or "")
    expertise = 0.7 if "bachelor" in edu or "master" in edu or "doctor" in edu else 0.45
    slug = re.sub(r"[^a-z0-9]+", "_", occupation.lower()).strip("_")[:24] or f"{niche}_{index}"
    return {
        "id": f"{slug}_{index}",
        "name": occupation.replace("_", " "),
        "role": str(row.get("professional_persona") or occupation)[:120],
        "interests": interests,
        "expertise": _clamp(expertise),
        "activity_level": 0.55,
        "novelty_seeking": 0.5,
        "promotional_tolerance": 0.3,
        "reply_tendency": 0.15,
        "repost_tendency": 0.18,
        "quote_tendency": 0.12,
        "share_tendency": 0.16,
        "click_tendency": 0.4,
        "follow_tendency": 0.06,
        "dwell_tendency": 0.5,
        "negative_sensitivity": 0.35,
        "evidence_demand": 0.45,
        "source": "nvidia/Nemotron-Personas-USA",
        "source_uuid": row.get("uuid"),
    }


def prepare(per_niche: int, max_scan: int, out_dir: Path, seed: int) -> dict:
    ds = load_dataset("nvidia/Nemotron-Personas-USA", split="train", streaming=True)
    ds = ds.shuffle(seed=seed, buffer_size=5_000)
    buckets: dict[str, list] = defaultdict(list)
    scanned = 0
    for row in ds:
        scanned += 1
        niche = route_niche(str(row.get("occupation") or ""), _parse_list(row.get("hobbies_and_interests_list")), str(row.get("persona") or ""))
        if niche and len(buckets[niche]) < per_niche:
            buckets[niche].append(to_persona(row, niche, len(buckets[niche]) + 1))
        if all(len(buckets[n]) >= per_niche for n in NICHES) or scanned >= max_scan:
            break
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for niche, personas in buckets.items():
        path = out_dir / f"{niche}_nemotron.json"
        path.write_text(json.dumps({"niche": niche, "source": "nvidia/Nemotron-Personas-USA", "license": "CC BY 4.0", "personas": personas}, indent=2), encoding="utf-8")
        written[niche] = len(personas)
    summary = {"scanned": scanned, "written": written, "out": str(out_dir)}
    (out_dir / "nemotron_prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-niche", type=int, default=8)
    parser.add_argument("--max-scan", type=int, default=30000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/processed/nemotron_packs")
    args = parser.parse_args()
    print(json.dumps(prepare(args.per_niche, args.max_scan, Path(args.out), args.seed), indent=2))


if __name__ == "__main__":
    main()
