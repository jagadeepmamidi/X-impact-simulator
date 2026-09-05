from __future__ import annotations

import numpy as np

from app.metrics import headline_impact_score
from app.schemas import PersonaReaction, RoundResult, SimulationSummary, SpreadAgent, SpreadGraph
from app.sim_config import SimulationConfig
from app.simulation import _sample_actions, simulate


def _reaction(persona_id: str = "a", **overrides: float) -> PersonaReaction:
    values: dict[str, float | str] = {
        "persona_id": persona_id,
        "topic_affinity": 0.6,
        "like_probability": 0.0,
        "reply_probability": 0.0,
        "repost_probability": 0.0,
        "quote_probability": 0.0,
        "share_probability": 0.0,
        "share_via_dm_probability": 0.0,
        "share_via_copy_link_probability": 0.0,
        "dwell_probability": 0.0,
        "click_probability": 0.0,
        "follow_probability": 0.0,
        "negative_feedback_probability": 0.0,
        "reason": "test",
    }
    values.update(overrides)
    return PersonaReaction(**values)


def test_compatible_actions_are_not_collapsed_to_one_category() -> None:
    reaction = _reaction(
        like_probability=1.0,
        reply_probability=1.0,
        repost_probability=1.0,
        quote_probability=1.0,
        share_probability=1.0,
        dwell_probability=1.0,
        click_probability=1.0,
        follow_probability=1.0,
    )

    events, primary = _sample_actions(
        reaction,
        np.random.default_rng(3),
        config=SimulationConfig(jitter_sigma=0.0, action_noise_sigma=0.0),
    )

    assert {"like", "reply", "repost", "quote", "share", "follow"}.issubset(events)
    assert "dwell" in events
    assert "click" in events
    assert primary in events


def test_sampling_uses_same_calibrated_probability_stream_as_scoring() -> None:
    calibrated = _reaction()
    misleading_affinity = _reaction(
        like_probability=1.0,
        reply_probability=1.0,
        repost_probability=1.0,
        quote_probability=1.0,
        share_probability=1.0,
        dwell_probability=1.0,
        click_probability=1.0,
        follow_probability=1.0,
    )
    config = SimulationConfig(
        jitter_sigma=0.0,
        action_noise_sigma=0.0,
        candidate_pool_size=1,
        candidate_top_k_in_network=1,
        candidate_top_k_out_of_network=1,
    )

    result = simulate(
        [calibrated],
        seed=7,
        users_per_persona=8,
        runs=1,
        max_rounds=1,
        population=8,
        boost=8,
        config=config,
        sample_reactions=[misleading_affinity],
    )

    shown = [agent for agent in result.graph.agents if agent.cohort != "origin"]
    assert shown
    assert all(agent.action == "ignore" for agent in shown)
    assert all(not agent.actions for agent in shown)


def test_visualized_graph_is_the_run_nearest_median_exposure(monkeypatch) -> None:
    exposures = iter((10, 90, 50))

    def fake_graph_run(*_args, **_kwargs):
        exposure = next(exposures)
        shown = exposure // 10
        agents = [
            SpreadAgent(
                id="POST",
                persona_id="post",
                name="Post",
                role="Origin",
                cohort="origin",
            )
        ]
        agents.extend(
            SpreadAgent(
                id=f"A{i}",
                persona_id="a",
                name="A",
                role="test",
                cohort="in_target" if i < shown else "never_shown",
            )
            for i in range(10)
        )
        round_row = RoundResult(
            round=1,
            audience_size=shown,
            likes=0,
            replies=0,
            reposts=0,
            follows=0,
            negatives=0,
            ignores=shown,
            score=float(exposure),
        )
        return [round_row], SpreadGraph(agents=agents, edges=[])

    monkeypatch.setattr("app.simulation.graph_run", fake_graph_run)
    result = simulate(
        [_reaction()],
        seed=1,
        users_per_persona=10,
        runs=3,
        max_rounds=1,
        population=10,
    )

    visible = [a for a in result.graph.agents if a.cohort not in {"origin", "never_shown"}]
    assert len(visible) == 5


def test_candidate_ranking_uses_both_network_branches(monkeypatch) -> None:
    seen: set[bool] = set()
    from app.ranking_policy import RankingDecision

    def fake_rank(_reaction, _rng, *, in_network, stage, config):
        seen.add(in_network)
        return RankingDecision("test", 50.0, 1, 1, True)

    monkeypatch.setattr("app.simulation.rank_target", fake_rank)
    config = SimulationConfig(
        in_network_target_rate=1.0,
        in_network_out_of_target_rate=0.0,
        candidate_pool_size=1,
        candidate_top_k_in_network=1,
        candidate_top_k_out_of_network=1,
        algo_exposure_rate=1.0,
        jitter_sigma=0.0,
        action_noise_sigma=0.0,
    )
    simulate(
        [_reaction("strong", topic_affinity=0.9), _reaction("weak", topic_affinity=0.1)],
        seed=9,
        users_per_persona=4,
        runs=1,
        max_rounds=2,
        population=8,
        boost=2,
        config=config,
        target_text="strong",
        topics=["strong"],
    )
    assert seen == {False, True}


def test_headline_score_includes_population_ranking_result() -> None:
    reaction = _reaction(like_probability=0.5)
    low = SimulationSummary(
        seed=1,
        runs=1,
        rounds=[],
        score_p10=10,
        score_p50=10,
        score_p90=10,
        reached_round_p50=1,
        out_of_network=False,
    )
    high = low.model_copy(update={"score_p50": 80.0})
    assert headline_impact_score([reaction], high) > headline_impact_score([reaction], low)
