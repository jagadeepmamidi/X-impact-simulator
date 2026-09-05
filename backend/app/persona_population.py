"""Validated, reproducible audience populations for the simulator.

Generated persona datasets are useful for display diversity, but they are not
behavioral ground truth.  This module keeps that distinction explicit:

* curated pack entries define behavior profiles;
* generated overlays may only provide sanitized display variants;
* every display variant records the behavior profile that drives it; and
* a seeded sampler produces stable, weighted population members.

The public interface is intentionally small: ``load_audience`` validates data
once, and ``sample_population`` materializes a deterministic population.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.schemas import Niche, Persona

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PACK_DIR = DATA_DIR / "packs"
OVERLAY_DIR = DATA_DIR / "overlays"

PERSONA_POPULATION_VERSION = "persona-population-v2.0"
SUPPORTED_NICHES = frozenset({"tech", "fitness", "finance", "comedy"})

_NICHE_TERMS: dict[str, tuple[str, ...]] = {
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

_SENSITIVE_KEYS = frozenset(
    {
        "age",
        "age_range",
        "birth_date",
        "date_of_birth",
        "sex",
        "gender",
        "race",
        "ethnicity",
        "religion",
        "political_affiliation",
        "marital_status",
        "sexual_orientation",
        "disability",
        "zip",
        "zip_code",
        "postal_code",
        "address",
    }
)
_MINOR_TEXT = re.compile(
    r"\b(?:"
    r"(?:[0-9]|1[0-7])[- ]year[- ]old|"
    r"infant|baby|toddler|minor|child|children|"
    r"elementary school|middle school|high school student|"
    r"nursery rhymes?|playdates?|crawling"
    r")\b",
    re.IGNORECASE,
)
_UNUSABLE_OCCUPATIONS = frozenset(
    {"", "unknown", "none", "not in workforce", "unemployed", "student"}
)
_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and as at by for from in into is it of on or the their to with who".split()
)


@dataclass(frozen=True)
class PersonaProvenance:
    source: str
    source_id: str
    version: str


@dataclass(frozen=True)
class DisplayPersona:
    id: str
    name: str
    role: str
    interests: tuple[str, ...]
    niche: str
    behavior_profile_id: str


@dataclass(frozen=True)
class BehaviorProfile:
    persona: Persona
    population_weight: float
    provenance: PersonaProvenance
    engagement_multiplier: float = 1.0
    skepticism_multiplier: float = 1.0

    @property
    def id(self) -> str:
        return self.persona.id


@dataclass(frozen=True)
class DisplayTemplate:
    display: DisplayPersona
    provenance: PersonaProvenance


@dataclass(frozen=True)
class RejectedPersona:
    source_id: str
    reason: str


@dataclass(frozen=True)
class AudienceDefinition:
    niche: str
    version: str
    source_hash: str
    behaviors: tuple[BehaviorProfile, ...]
    displays: tuple[DisplayTemplate, ...]
    rejections: tuple[RejectedPersona, ...]

    def behavior(self, profile_id: str) -> BehaviorProfile:
        for profile in self.behaviors:
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown behavior profile: {profile_id}")


@dataclass(frozen=True)
class PopulationMember:
    stable_id: str
    display: DisplayPersona
    behavior: BehaviorProfile
    population_weight: float
    provenance: PersonaProvenance

    def as_persona(self) -> Persona:
        """Return one coherent legacy Persona for existing model interfaces."""

        source = self.behavior.persona
        engage = self.behavior.engagement_multiplier
        skepticism = self.behavior.skepticism_multiplier

        def bounded(value: float) -> float:
            return round(max(0.0, min(1.0, value)), 6)

        return self.behavior.persona.model_copy(
            update={
                "id": self.stable_id,
                "name": self.display.name,
                "role": self.display.role,
                "interests": list(self.display.interests),
                "activity_level": bounded(source.activity_level * engage),
                "reply_tendency": bounded(source.reply_tendency * engage),
                "repost_tendency": bounded(source.repost_tendency * engage),
                "quote_tendency": bounded(source.quote_tendency * engage),
                "share_tendency": bounded(source.share_tendency * engage),
                "click_tendency": bounded(source.click_tendency * engage),
                "follow_tendency": bounded(source.follow_tendency * engage),
                "dwell_tendency": bounded(source.dwell_tendency * engage),
                "negative_sensitivity": bounded(
                    source.negative_sensitivity * skepticism
                ),
                "evidence_demand": bounded(source.evidence_demand * skepticism),
                "promotional_tolerance": bounded(
                    source.promotional_tolerance / skepticism
                ),
            }
        )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(value.lower())
        if len(token) > 2 and token not in _STOPWORDS
    }


def _clean_text(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _source_id(item: dict) -> str:
    prepared = str(item.get("source_id") or "")
    if re.fullmatch(r"[0-9a-f]{16}", prepared):
        return prepared
    raw = str(
        prepared
        or item.get("source_uuid")
        or item.get("uuid")
        or item.get("id")
        or "unknown"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _minor_reason(item: dict) -> str | None:
    for key in ("age", "age_years", "age_range"):
        raw = item.get(key)
        if raw is None:
            continue
        try:
            if float(raw) < 18:
                return "minor_age"
        except (TypeError, ValueError):
            ages = [int(value) for value in re.findall(r"\d{1,3}", str(raw))]
            if (ages and min(ages) < 18) or _MINOR_TEXT.search(str(raw)):
                return "minor_age"

    searchable = " ".join(
        str(item.get(key) or "")
        for key in ("name", "role", "persona", "professional_persona", "interests")
    )
    searchable = re.sub(r"[‐‑‒–—−]", "-", searchable)
    if _MINOR_TEXT.search(searchable):
        return "minor_description"
    return None


def _niche_hits(niche: str, text: str) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(term for term in _NICHE_TERMS[niche] if term in lowered)


def _safe_interests(
    raw_interests: Iterable[object],
    niche: str,
    behavior: Persona,
) -> tuple[str, ...]:
    safe: list[str] = []
    behavior_tokens = _tokens(
        f"{behavior.name} {behavior.role} {' '.join(behavior.interests)}"
    )
    for raw in raw_interests:
        value = _clean_text(raw, 60)
        if not value or _MINOR_TEXT.search(value):
            continue
        value_tokens = _tokens(value)
        if _niche_hits(niche, value) or value_tokens & behavior_tokens:
            if value.lower() not in {existing.lower() for existing in safe}:
                safe.append(value)
        if len(safe) >= 4:
            break
    if not safe:
        safe.extend(behavior.interests[:4])
    return tuple(safe)


def _overlay_behavior(
    niche: str,
    item: dict,
    behaviors: tuple[BehaviorProfile, ...],
) -> BehaviorProfile | None:
    identity_text = " ".join(
        [
            str(item.get("name") or ""),
            str(item.get("role") or ""),
        ]
    )
    if not _niche_hits(niche, identity_text):
        return None

    raw_interests = item.get("interests") or []
    if not isinstance(raw_interests, (list, tuple, set)):
        raw_interests = [raw_interests]
    source_text = f"{identity_text} " + " ".join(str(value) for value in raw_interests)

    source_tokens = _tokens(source_text)
    try:
        source_expertise = float(item.get("expertise", 0.5))
    except (TypeError, ValueError):
        source_expertise = 0.5

    ranked: list[tuple[float, str, BehaviorProfile]] = []
    for profile in behaviors:
        persona = profile.persona
        behavior_text = f"{persona.name} {persona.role} {' '.join(persona.interests)}"
        overlap = len(source_tokens & _tokens(behavior_text))
        expertise_fit = 1.0 - min(1.0, abs(source_expertise - persona.expertise))
        niche_overlap = len(_niche_hits(niche, behavior_text))
        score = 3.0 * overlap + expertise_fit + 0.25 * niche_overlap
        ranked.append((score, persona.id, profile))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked[0][2] if ranked else None


def _sanitize_overlay(
    niche: str,
    item: dict,
    behaviors: tuple[BehaviorProfile, ...],
    source: str,
) -> tuple[DisplayTemplate | None, RejectedPersona | None]:
    sid = _source_id(item)
    reason = _minor_reason(item)
    if reason:
        return None, RejectedPersona(source_id=sid, reason=reason)

    occupation = _clean_text(item.get("name") or item.get("occupation"), 60)
    if occupation.lower() in _UNUSABLE_OCCUPATIONS:
        return None, RejectedPersona(source_id=sid, reason="unusable_identity")

    behavior = _overlay_behavior(niche, item, behaviors)
    if behavior is None:
        return None, RejectedPersona(source_id=sid, reason="niche_mismatch")

    # The free-form generated biography may contain names, exact ages, location,
    # or inferred sensitive traits.  Runtime display text is reconstructed only
    # from generic occupation and the curated behavior archetype.
    display_name = (
        occupation.title()
        if _niche_hits(niche, occupation)
        else behavior.persona.name
    )
    display_role = f"{display_name} · {behavior.persona.role}"[:100]
    raw_interests = item.get("interests") or []
    if not isinstance(raw_interests, (list, tuple, set)):
        raw_interests = [raw_interests]
    interests = _safe_interests(raw_interests, niche, behavior.persona)
    source_name = _clean_text(source, 80) or "generated-overlay"
    provenance = PersonaProvenance(
        source=source_name,
        source_id=sid,
        version=PERSONA_POPULATION_VERSION,
    )
    display = DisplayPersona(
        id=f"overlay:{niche}:{sid}",
        name=display_name,
        role=display_role,
        interests=interests,
        niche=niche,
        behavior_profile_id=behavior.id,
    )
    return DisplayTemplate(display=display, provenance=provenance), None


def _validated_behavior(item: dict, niche: str) -> Persona:
    persona = Persona.model_validate(item)
    if not persona.id.strip() or not persona.name.strip() or not persona.role.strip():
        raise ValueError(f"{niche} pack contains a persona with empty identity fields")
    if not persona.interests:
        raise ValueError(f"{niche}:{persona.id} must contain at least one interest")

    values = (
        persona.expertise,
        persona.activity_level,
        persona.novelty_seeking,
        persona.promotional_tolerance,
        persona.reply_tendency,
        persona.repost_tendency,
        persona.quote_tendency,
        persona.share_tendency,
        persona.click_tendency,
        persona.follow_tendency,
        persona.dwell_tendency,
        persona.negative_sensitivity,
        persona.evidence_demand,
    )
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        raise ValueError(f"{niche}:{persona.id} contains a behavior value outside [0, 1]")
    return persona


def _normalized_behaviors(personas: list[Persona], niche: str) -> tuple[BehaviorProfile, ...]:
    # Activity is a modest prevalence prior for an active-feed simulation.  The
    # floor keeps quieter archetypes represented rather than collapsing the pack.
    raw_weights = [0.65 + 0.35 * persona.activity_level for persona in personas]
    total = sum(raw_weights)
    profiles: list[BehaviorProfile] = []
    for persona, raw_weight in zip(personas, raw_weights, strict=True):
        profiles.append(
            BehaviorProfile(
                persona=persona,
                population_weight=raw_weight / total,
                provenance=PersonaProvenance(
                    source=f"curated-pack:{niche}",
                    source_id=persona.id,
                    version=PERSONA_POPULATION_VERSION,
                ),
            )
        )
    return tuple(profiles)


def load_audience(
    niche: Niche | str,
    *,
    pack_dir: Path = PACK_DIR,
    overlay_dir: Path = OVERLAY_DIR,
) -> AudienceDefinition:
    """Load and validate one audience definition.

    Invalid curated behavior data is a hard error.  Unsafe, underage, irrelevant,
    or malformed display overlays are rejected and recorded without weakening the
    curated audience.
    """

    niche_value = str(niche).lower()
    if niche_value not in SUPPORTED_NICHES:
        raise ValueError(f"Unsupported niche: {niche}")

    pack_path = Path(pack_dir) / f"{niche_value}.json"
    raw_pack = json.loads(pack_path.read_text(encoding="utf-8"))
    raw_personas = raw_pack.get("personas")
    if not isinstance(raw_personas, list) or not raw_personas:
        raise ValueError(f"{pack_path} does not contain a non-empty persona pack")

    personas = [_validated_behavior(item, niche_value) for item in raw_personas]
    ids = [persona.id for persona in personas]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{pack_path} contains duplicate persona ids")
    behaviors = _normalized_behaviors(personas, niche_value)

    displays: list[DisplayTemplate] = [
        DisplayTemplate(
            display=DisplayPersona(
                id=f"curated:{niche_value}:{profile.id}",
                name=profile.persona.name,
                role=profile.persona.role,
                interests=tuple(profile.persona.interests),
                niche=niche_value,
                behavior_profile_id=profile.id,
            ),
            provenance=profile.provenance,
        )
        for profile in behaviors
    ]
    rejections: list[RejectedPersona] = []

    overlay_path = Path(overlay_dir) / f"{niche_value}.json"
    if overlay_path.is_file():
        try:
            raw_overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raw_overlay = None
            rejections.append(
                RejectedPersona(source_id="overlay-file", reason="malformed_overlay_file")
            )
        if isinstance(raw_overlay, dict):
            source = str(raw_overlay.get("source") or "generated-overlay")
            raw_items = raw_overlay.get("personas") or []
            if not isinstance(raw_items, list):
                rejections.append(
                    RejectedPersona(source_id="overlay-file", reason="malformed_overlay_file")
                )
                raw_items = []
            for item in raw_items:
                if not isinstance(item, dict):
                    rejections.append(
                        RejectedPersona(source_id="unknown", reason="malformed")
                    )
                    continue
                display, rejection = _sanitize_overlay(
                    niche_value, item, behaviors, source
                )
                if display is not None:
                    displays.append(display)
                if rejection is not None:
                    rejections.append(rejection)

    canonical = {
        "niche": niche_value,
        "version": PERSONA_POPULATION_VERSION,
        "behaviors": [
            {
                "persona": profile.persona.model_dump(mode="json"),
                "weight": profile.population_weight,
                "source": profile.provenance.source,
            }
            for profile in behaviors
        ],
        "displays": [
            {
                "id": template.display.id,
                "name": template.display.name,
                "role": template.display.role,
                "interests": template.display.interests,
                "behavior": template.display.behavior_profile_id,
                "source": template.provenance.source,
                "source_id": template.provenance.source_id,
                "source_version": template.provenance.version,
            }
            for template in displays
        ],
    }
    source_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return AudienceDefinition(
        niche=niche_value,
        version=PERSONA_POPULATION_VERSION,
        source_hash=source_hash,
        behaviors=behaviors,
        displays=tuple(displays),
        rejections=tuple(rejections),
    )


def _weighted_profile_ids(
    profiles: tuple[BehaviorProfile, ...], size: int, rng: random.Random
) -> list[str]:
    exact = [profile.population_weight * size for profile in profiles]
    counts = [math.floor(value) for value in exact]
    remaining = size - sum(counts)
    order = list(range(len(profiles)))
    rng.shuffle(order)
    order.sort(key=lambda index: exact[index] - counts[index], reverse=True)
    for index in order[:remaining]:
        counts[index] += 1
    ids = [profile.id for profile, count in zip(profiles, counts, strict=True) for _ in range(count)]
    rng.shuffle(ids)
    return ids


def _clamp_multiplier(value: float) -> float:
    return round(max(0.7, min(1.3, value)), 6)


def sample_population(
    audience: AudienceDefinition,
    size: int,
    *,
    seed: int,
) -> list[PopulationMember]:
    """Materialize a deterministic, weighted, behaviorally coherent population."""

    if size <= 0:
        raise ValueError("Population size must be positive")
    if not audience.behaviors:
        raise ValueError("Audience has no behavior profiles")

    rng = random.Random(seed)
    profile_ids = _weighted_profile_ids(audience.behaviors, size, rng)
    displays_by_behavior: dict[str, list[DisplayTemplate]] = {
        profile.id: [] for profile in audience.behaviors
    }
    for template in audience.displays:
        displays_by_behavior[template.display.behavior_profile_id].append(template)

    members: list[PopulationMember] = []
    for index, profile_id in enumerate(profile_ids):
        base = audience.behavior(profile_id)
        candidates = displays_by_behavior[profile_id]
        template = candidates[rng.randrange(len(candidates))]

        # A shared engagement latent moves observable engagement tendencies
        # together.  Skepticism is partially inverse-correlated, while retaining
        # independent noise.  This avoids unrealistic independent trait jitter.
        engagement_latent = rng.gauss(0.0, 0.09)
        skepticism_latent = -0.4 * engagement_latent + rng.gauss(0.0, 0.06)
        behavior = BehaviorProfile(
            persona=base.persona,
            population_weight=base.population_weight,
            provenance=base.provenance,
            engagement_multiplier=_clamp_multiplier(math.exp(engagement_latent)),
            skepticism_multiplier=_clamp_multiplier(math.exp(skepticism_latent)),
        )
        digest_input = (
            f"{audience.source_hash}:{seed}:{index}:{template.display.id}:{profile_id}"
        )
        stable_id = "member:" + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
        members.append(
            PopulationMember(
                stable_id=stable_id,
                display=template.display,
                behavior=behavior,
                population_weight=base.population_weight,
                provenance=template.provenance,
            )
        )
    return members


__all__ = [
    "AudienceDefinition",
    "BehaviorProfile",
    "DisplayPersona",
    "PERSONA_POPULATION_VERSION",
    "PersonaProvenance",
    "PopulationMember",
    "RejectedPersona",
    "load_audience",
    "sample_population",
]
