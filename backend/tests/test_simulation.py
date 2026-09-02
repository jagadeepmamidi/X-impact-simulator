from app.schemas import PersonaReaction
from app.scoring import OON_WEIGHT_FACTOR, audience_score, ranking_score
from app.simulation import heuristic_reactions, load_overlays, load_pack, simulate


def _reaction(pid: str, like: float, **extra) -> PersonaReaction:
    payload = dict(
        persona_id=pid,
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


def test_same_seed_reproducible() -> None:
    reactions = [_reaction("a", 0.6), _reaction("b", 0.2)]
    a = simulate(reactions, seed=7, users_per_persona=8, runs=5, max_rounds=4)
    b = simulate(reactions, seed=7, users_per_persona=8, runs=5, max_rounds=4)
    assert a.model_dump() == b.model_dump()


def test_tech_pack_loads() -> None:
    for niche in ("tech", "fitness", "finance", "comedy"):
        pack = load_pack(niche)
        assert len(pack) == 15, niche
        assert len(load_overlays(niche)) >= 1, niche
    pack = load_pack("tech")
    reactions = heuristic_reactions(
        pack,
        {
            "topics": ["AI tools", "open source"],
            "hook_strength": 0.8,
            "clarity": 0.7,
            "novelty": 0.6,
            "promotional_intensity": 0.1,
            "controversy": 0.1,
            "visual_hook": 0.0,
        },
    )
    score = audience_score(reactions)
    assert 0 <= score <= 100
    assert all(r.persona_id for r in reactions)
    assert all(r.quote_probability >= 0 for r in reactions)


def test_favorite_weight_matches_param_rs() -> None:
    r = _reaction("a", 1.0, reply_probability=0, repost_probability=0, dwell_probability=0, follow_probability=0, negative_feedback_probability=0)
    assert abs(ranking_score([r], in_network=True) - 0.501) < 1e-9


def test_oon_multiplies_after_offset() -> None:
    r = _reaction("a", 1.0, reply_probability=0, repost_probability=0, dwell_probability=0, follow_probability=0, negative_feedback_probability=0)
    inn = ranking_score([r], in_network=True)
    oon = ranking_score([r], in_network=False)
    assert abs(oon - inn * OON_WEIGHT_FACTOR) < 1e-12


def test_report_uses_negative_offset_path() -> None:
    r = _reaction(
        "a",
        0.0,
        reply_probability=0,
        repost_probability=0,
        dwell_probability=0,
        follow_probability=0,
        negative_feedback_probability=0,
        report_probability=1.0,
    )
    raw = ranking_score([r], in_network=True)
    assert raw < 0.001
    assert raw >= 0.0


def test_spread_graph_blobs_and_edges() -> None:
    pack = load_pack("tech")
    reactions = heuristic_reactions(
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
    sim = simulate(
        reactions,
        seed=11,
        users_per_persona=5,
        runs=3,
        max_rounds=4,
        personas=pack,
        population=40,
        boost=6,
        target_text="Software engineers, AI tools, tutorials",
        topics=["AI tools"],
        overlays=load_overlays("tech"),
    )
    people = [a for a in sim.graph.agents if a.cohort != "origin"]
    shown = [a for a in people if a.cohort != "never_shown"]
    assert len(people) == 40
    overlays = load_overlays("tech")
    overlay_names = {p.name for p in overlays}
    clone_names = {a.name for a in people}
    assert overlay_names & clone_names
    assert len([a for a in people if a.shown_round == 1]) == 6
    assert len({a.persona_id for a in people if a.shown_round == 1}) == 6
    assert any(a.cohort == "in_target" for a in shown)
    assert any(a.cohort == "out_of_target" for a in shown)
    assert any(a.in_target for a in people)
    assert any(not a.in_target for a in people)
    assert any(a.cohort == "never_shown" for a in people) or len(sim.graph.edges) >= 6
    assert any(e.source == "POST" and e.kind == "algo" for e in sim.graph.edges)
    assert all(e.kind in ("share", "algo") for e in sim.graph.edges)
    assert len(sim.rounds) >= 3
    assert max(e.round for e in sim.graph.edges) >= 3
