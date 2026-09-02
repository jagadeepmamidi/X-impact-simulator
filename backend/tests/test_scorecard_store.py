from app.calibration import calibrate_reactions
from app.heads import FAVORITE_BLEND, HEADS_NOTE, RETWEET_BLEND
from app.metrics import scorecard
from app.schemas import ContentFeatures, Explanation, ImpactReport, SimulationSummary
from app.simulation import heuristic_reactions, load_pack, simulate
from app.store import load_report, save_report


def test_scorecard_bounds() -> None:
    pack = load_pack("tech")
    affinities = heuristic_reactions(
        pack,
        {
            "topics": ["AI tools"],
            "hook_strength": 0.8,
            "clarity": 0.7,
            "novelty": 0.6,
            "promotional_intensity": 0.1,
            "controversy": 0.1,
            "visual_hook": 0.0,
        },
    )
    reactions = calibrate_reactions(affinities)
    sim = simulate(
        reactions,
        seed=3,
        users_per_persona=2,
        runs=5,
        max_rounds=3,
        personas=pack,
        population=40,
        boost=6,
        sample_reactions=affinities,
    )
    card = scorecard(reactions, pack, ContentFeatures(topics=["AI tools"]), sim)
    for key in (
        "audience_fit",
        "niche_index",
        "negative_signal_risk",
        "stability",
        "confidence",
        "reach_pct",
        "distribution_potential",
        "engagement_quality",
        "profile_impact",
    ):
        assert 0 <= card[key] <= 100
    assert card["stability"] == card["confidence"]
    assert isinstance(card["stop_reason"], str)
    assert card["stop_reason"]


def test_store_roundtrip() -> None:
    report = ImpactReport(
        disclaimer="x",
        niche="tech",
        groq_used=False,
        content=ContentFeatures(),
        reactions=[],
        simulation=SimulationSummary(
            seed=9,
            runs=3,
            rounds=[],
            score_p10=12,
            score_p50=20,
            score_p90=28,
            reached_round_p50=2,
            out_of_network=False,
        ),
        impact_score=20,
        explanation=Explanation(headline="h", summary="s", suggestions=["rewrite the hook"]),
        weights_note="w",
        niche_index=41.5,
        audience_fit=50,
        heads_note=HEADS_NOTE,
    )
    run_id = save_report(report)
    loaded = load_report(run_id)
    assert loaded is not None
    assert loaded.run_id == run_id
    assert loaded.niche == "tech"
    assert loaded.niche_index == 41.5
    assert loaded.explanation.suggestions == ["rewrite the hook"]
    assert save_report(loaded) == run_id


def test_heads_favorite_retweet_only() -> None:
    assert FAVORITE_BLEND == 0.40
    assert RETWEET_BLEND == 0.25
    low = HEADS_NOTE.lower()
    assert "favorite" in low and "retweet" in low
    assert "40%" in HEADS_NOTE and "25%" in HEADS_NOTE
