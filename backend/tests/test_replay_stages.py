from app.calibration import calibrate_reactions
from app.pipeline import replay_report, run_pipeline
from app.simulation import heuristic_reactions, load_pack, simulate
from app.store import load_outcome, save_outcome
from app.schemas import OutcomeRecord


def test_rounds_use_distribution_stages() -> None:
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
    sim = simulate(
        calibrate_reactions(affinities),
        seed=11,
        users_per_persona=2,
        runs=3,
        max_rounds=6,
        personas=pack,
        population=40,
        boost=6,
        target_text="Software engineers, AI tools, tutorials",
        topics=["AI tools"],
        sample_reactions=affinities,
    )
    expected = ["seed", "adjacent", "niche", "general"]
    stages = [row.stage for row in sim.rounds]
    assert stages[0] == "seed"
    for i, stage in enumerate(stages):
        assert stage == expected[min(i, 3)]


def test_replay_same_seed_matches_graph() -> None:
    source = run_pipeline(
        "tech",
        "We open-sourced a 12ms eval harness for local LLMs.",
        [],
        None,
        seed=3,
        population=40,
        persist=True,
    )
    assert source.affinity_reactions
    replayed = replay_report(source, persist=False)
    assert replayed.parent_run_id == source.run_id
    assert replayed.inference_path == "replay+stored-probabilities"
    assert replayed.groq_used is False
    assert replayed.replay_mode == "exact"
    assert replayed.config_snapshot["seed"] == source.config_snapshot["seed"]
    assert replayed.snapshot_hash != source.snapshot_hash
    assert replayed.simulation.graph.model_dump() == source.simulation.graph.model_dump()
    assert replayed.simulation.rounds == source.simulation.rounds


def test_replay_with_new_seed_records_variant_provenance() -> None:
    source = run_pipeline(
        "tech",
        "We open-sourced a 12ms eval harness for local LLMs.",
        [],
        None,
        seed=3,
        population=40,
        persist=False,
    )

    replayed = replay_report(source, seed=17, persist=False)

    assert replayed.replay_mode == "seed-variant"
    assert replayed.replayable is True
    assert replayed.simulation.seed == 17
    assert replayed.config_snapshot["seed"] == 17
    assert replayed.provenance["replay_exact_parent_match"] is False
    assert replayed.snapshot_hash != source.snapshot_hash
    assert any("seed variant" in limitation for limitation in replayed.replay_limitations)


def test_outcome_roundtrip() -> None:
    report = run_pipeline("tech", "hello", [], None, seed=5, population=40, persist=True)
    saved = save_outcome(
        OutcomeRecord(run_id=report.run_id or "", impressions=1200, likes=40, replies=3, reposts=2, follows=1)
    )
    loaded = load_outcome(saved.run_id)
    assert loaded is not None
    assert loaded.impressions == 1200
    assert loaded.likes == 40
