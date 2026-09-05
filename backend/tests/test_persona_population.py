import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.persona_population import load_audience, sample_population

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))
from prepare_nemotron import route_niche, to_persona


@pytest.mark.parametrize("niche", ["tech", "fitness", "finance", "comedy"])
def test_audience_weights_and_identity_mapping(niche: str) -> None:
    audience = load_audience(niche)
    behavior_ids = {profile.id for profile in audience.behaviors}

    assert len(audience.behaviors) == 15
    assert sum(profile.population_weight for profile in audience.behaviors) == pytest.approx(1.0)
    assert len(audience.source_hash) == 64
    assert len(audience.displays) >= len(audience.behaviors)
    assert all(template.display.niche == niche for template in audience.displays)
    assert all(
        template.display.behavior_profile_id in behavior_ids
        for template in audience.displays
    )
    assert all(0.0 < profile.population_weight < 0.15 for profile in audience.behaviors)


def test_population_sampling_is_deterministic_correlated_and_diverse() -> None:
    audience = load_audience("tech")
    first = sample_population(audience, 500, seed=412)
    second = sample_population(audience, 500, seed=412)
    different = sample_population(audience, 500, seed=413)

    assert first == second
    assert [member.stable_id for member in first] != [
        member.stable_id for member in different
    ]
    assert len({member.stable_id for member in first}) == 500
    assert all(
        member.display.behavior_profile_id == member.behavior.id for member in first
    )

    counts = Counter(member.behavior.id for member in first)
    assert len(counts) == len(audience.behaviors)
    assert max(counts.values()) / len(first) < 0.09
    assert len({member.behavior.engagement_multiplier for member in first}) > 100

    engagement = [member.behavior.engagement_multiplier - 1.0 for member in first]
    skepticism = [member.behavior.skepticism_multiplier - 1.0 for member in first]
    covariance = sum(a * b for a, b in zip(engagement, skepticism, strict=True))
    assert covariance < 0.0

    for member in first[:25]:
        legacy = member.as_persona()
        assert legacy.id == member.stable_id
        assert legacy.name == member.display.name
        assert legacy.role == member.display.role
        assert legacy.expertise == member.behavior.persona.expertise
    assert any(
        member.as_persona().reply_tendency
        != member.behavior.persona.reply_tendency
        for member in first
    )


def test_unsafe_and_irrelevant_overlays_are_rejected(tmp_path: Path) -> None:
    overlays = {
        "niche": "tech",
        "source": "test/generated",
        "personas": [
            {
                "id": "minor-by-age",
                "uuid": "minor-age-uuid",
                "name": "Software Developer",
                "role": "Developer learning Python",
                "interests": ["Python"],
                "age": 17,
            },
            {
                "id": "minor-by-text",
                "uuid": "minor-text-uuid",
                "name": "Software Developer",
                "role": "A 16-year-old developer learning JavaScript",
                "interests": ["JavaScript"],
            },
            {
                "id": "wrong-niche",
                "uuid": "wrong-niche-uuid",
                "name": "Financial Clerk",
                "role": "Maintains accounting ledgers",
                "interests": ["Bookkeeping"],
            },
            {
                "id": "safe-adult",
                "uuid": "safe-adult-uuid",
                "name": "Software Developer",
                "role": "Alex Example, a software developer working in Python",
                "interests": ["Python", "church choir", "local politics"],
                "gender": "synthetic-sensitive-value",
                "zip_code": "00000",
                "expertise": 0.7,
            },
        ],
    }
    (tmp_path / "tech.json").write_text(json.dumps(overlays), encoding="utf-8")

    audience = load_audience("tech", overlay_dir=tmp_path)
    generated = [
        template
        for template in audience.displays
        if template.provenance.source == "test/generated"
    ]
    reasons = Counter(rejection.reason for rejection in audience.rejections)

    assert len(generated) == 1
    assert reasons == {
        "minor_age": 1,
        "minor_description": 1,
        "niche_mismatch": 1,
    }
    display = generated[0].display
    assert display.name == "Software Developer"
    assert "Alex Example" not in display.role
    assert "church" not in " ".join(display.interests).lower()
    assert "politic" not in " ".join(display.interests).lower()
    assert generated[0].provenance.source_id != "safe-adult-uuid"
    assert not re.search(r"\b(?:gender|zip|age)\b", repr(display), re.IGNORECASE)


def test_current_finance_minor_is_not_loaded_at_runtime() -> None:
    audience = load_audience("finance")
    assert any(
        rejection.reason in {"minor_age", "minor_description"}
        for rejection in audience.rejections
    )
    runtime_text = " ".join(
        f"{template.display.name} {template.display.role} {' '.join(template.display.interests)}"
        for template in audience.displays
    ).lower()
    assert "1-year-old" not in runtime_text
    assert "nursery rhyme" not in runtime_text


def test_nemotron_conversion_is_safe_varied_and_high_precision() -> None:
    minor = {
        "uuid": "minor",
        "occupation": "software developer",
        "age": 12,
        "professional_persona": "A Python learner",
    }
    assert to_persona(minor, "tech", 1) is None

    first_row = {
        "uuid": "adult-one",
        "occupation": "software developer",
        "professional_persona": "Taylor Example builds Python cloud systems",
        "skills_and_expertise_list": ["Python", "Cloud software"],
        "hobbies_and_interests_list": ["church choir", "local politics"],
        "education_level": "Bachelor degree",
        "age": 34,
        "gender": "synthetic-sensitive-value",
    }
    second_row = {
        "uuid": "adult-two",
        "occupation": "machine learning researcher",
        "professional_persona": "Jordan Example evaluates machine learning systems",
        "skills_and_expertise_list": ["Machine learning", "Data science"],
        "hobbies_and_interests_list": ["community theatre"],
        "education_level": "Doctorate",
        "age": 48,
    }
    first = to_persona(first_row, "tech", 1)
    second = to_persona(second_row, "tech", 2)

    assert first is not None and second is not None
    assert route_niche("mechanical engineer", [], "designs bridges") is None
    assert route_niche("software developer", [], "builds Python services") == "tech"
    assert route_niche("financial clerk", [], "maintains accounting ledgers") == "finance"
    for converted, personal_name in ((first, "Taylor Example"), (second, "Jordan Example")):
        assert personal_name not in str(converted)
        assert "uuid" not in converted
        assert "age" not in converted
        assert "gender" not in converted
        assert converted["behavior_semantics"] == "derived_simulation_prior_not_observed_label"
        assert len(str(converted["source_id"])) == 16

    behavior_fields = (
        "activity_level",
        "novelty_seeking",
        "promotional_tolerance",
        "reply_tendency",
        "repost_tendency",
        "evidence_demand",
    )
    assert any(first[field] != second[field] for field in behavior_fields)
