from app.calibration import (
    IMPRESSION_PRIORS,
    calibrate_probability,
    calibrate_reactions,
    to_ui_score,
)
from app.schemas import PersonaReaction
from app.scoring import audience_score, ranking_score
from app.simulation import heuristic_reactions, load_pack, simulate


def _features(**overrides) -> dict:
    base = {
        "topics": ["AI tools", "open source"],
        "hook_strength": 0.8,
        "clarity": 0.7,
        "novelty": 0.6,
        "promotional_intensity": 0.1,
        "controversy": 0.1,
        "visual_hook": 0.0,
    }
    base.update(overrides)
    return base


def _reaction(like: float, **extra) -> PersonaReaction:
    payload = dict(
        persona_id="a",
        topic_affinity=0.7,
        like_probability=like,
        reply_probability=0.1,
        repost_probability=0.1,
        dwell_probability=0.5,
        follow_probability=0.05,
        negative_feedback_probability=0.02,
        reason="test",
    )
    payload.update(extra)
    return PersonaReaction(**payload)


def test_affinity_half_maps_to_prior() -> None:
    prior = IMPRESSION_PRIORS["like_probability"]
    assert abs(calibrate_probability(0.5, prior) - prior) < 1e-9


def test_zero_affinity_stays_zero() -> None:
    assert calibrate_probability(0.0, 0.03) == 0.0


def test_high_affinity_does_not_saturate_copy_link() -> None:
    p = calibrate_probability(0.95, IMPRESSION_PRIORS["share_via_copy_link_probability"])
    assert p < 0.01


def test_generous_llm_affinities_do_not_hit_ui_100() -> None:
    r = _reaction(
        0.85,
        reply_probability=0.55,
        quote_probability=0.4,
        share_probability=0.35,
        share_via_dm_probability=0.2,
        share_via_copy_link_probability=0.25,
        follow_probability=0.3,
        click_probability=0.5,
    )
    calibrated = calibrate_reactions([r])[0]
    ui = audience_score([calibrated])
    assert ui < 95
    assert calibrated.share_via_copy_link_probability < 0.01


def test_weak_content_scores_below_strong() -> None:
    pack = load_pack("tech")
    weak = calibrate_reactions(
        heuristic_reactions(
            pack,
            _features(
                topics=["hello"],
                hook_strength=0.1,
                clarity=0.2,
                novelty=0.1,
                promotional_intensity=0.2,
            ),
        )
    )
    strong = calibrate_reactions(heuristic_reactions(pack, _features()))
    promo = calibrate_reactions(
        heuristic_reactions(
            pack,
            _features(topics=["buy", "discount", "sale"], promotional_intensity=0.95, hook_strength=0.3),
        )
    )
    weak_ui = audience_score(weak)
    strong_ui = audience_score(strong)
    promo_ui = audience_score(promo)
    assert 0 < weak_ui < strong_ui
    assert promo_ui < strong_ui
    assert strong_ui < 98
    assert weak_ui < 80


def test_like_monotonic_after_calibration() -> None:
    low = calibrate_reactions([_reaction(0.2)])[0]
    high = calibrate_reactions([_reaction(0.9)])[0]
    assert ranking_score([high]) > ranking_score([low])


def test_ui_mapping_is_not_raw_over_six() -> None:
    assert to_ui_score(6.0) == 100.0
    mid = to_ui_score(0.08)
    assert 45 <= mid <= 55


def test_monte_carlo_percentiles_are_final_cascade_scores() -> None:
    pack = load_pack("tech")
    affinities = heuristic_reactions(pack, _features())
    reactions = calibrate_reactions(affinities)
    sim = simulate(
        reactions,
        seed=11,
        users_per_persona=2,
        runs=8,
        max_rounds=4,
        personas=pack,
        population=40,
        boost=6,
        target_text="Software engineers, AI tools, tutorials",
        topics=["AI tools"],
        sample_reactions=affinities,
    )
    assert sim.rounds
    final = sim.rounds[-1].score
    assert sim.score_p10 <= sim.score_p50 <= sim.score_p90
    assert sim.score_p10 - 15 <= final <= sim.score_p90 + 15
    assert sim.exposure_p50 >= 0
    people = [a for a in sim.graph.agents if a.cohort != "origin"]
    assert len(people) == 40
