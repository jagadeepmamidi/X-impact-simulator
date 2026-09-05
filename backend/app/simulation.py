from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.schemas import (
    Action,
    Persona,
    PersonaReaction,
    RoundResult,
    SimulationSummary,
    SpreadAgent,
    SpreadEdge,
    SpreadGraph,
)
from app.ranking_policy import RankingDecision, rank_target
from app.scoring import clamp01, ranking_score, to_ui_score
from app.sim_config import DEFAULT_SIM_CONFIG, SimulationConfig

if TYPE_CHECKING:
    from app.persona_population import PopulationMember

PACK_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"
OVERLAY_DIR = Path(__file__).resolve().parent.parent / "data" / "overlays"
ACTIONS: list[Action] = [
    "ignore",
    "like",
    "reply",
    "repost",
    "quote",
    "share",
    "follow",
    "negative",
]
PROB_FIELDS = (
    "like_probability",
    "reply_probability",
    "repost_probability",
    "quote_probability",
    "share_probability",
    "share_via_dm_probability",
    "share_via_copy_link_probability",
    "dwell_probability",
    "click_probability",
    "photo_expand_probability",
    "video_open_probability",
    "open_link_probability",
    "quoted_click_probability",
    "follow_probability",
    "post_unexplored_probability",
    "not_interested_probability",
    "mute_probability",
    "block_probability",
    "report_probability",
    "not_dwelled_probability",
    "negative_feedback_probability",
)
NEGATIVE_PROB_FIELDS = frozenset(
    {
        "not_interested_probability",
        "mute_probability",
        "block_probability",
        "report_probability",
        "not_dwelled_probability",
        "negative_feedback_probability",
    }
)


def load_pack(niche: str) -> list[Persona]:
    path = PACK_DIR / f"{niche}.json"
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Persona.model_validate(item) for item in raw["personas"]]


def load_overlays(niche: str) -> list[Persona]:
    path = OVERLAY_DIR / f"{niche}.json"
    if not path.is_file():
        return []
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[Persona] = []
    for item in raw.get("personas") or []:
        try:
            out.append(Persona.model_validate(item))
        except Exception:
            continue
    return out


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


_STOP = frozenset(
    "the and for with this that from your are was you not but how why who what when".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in _STOP]


def _stem_hit(token: str, hay: str) -> bool:
    if token in hay:
        return True
    return any(
        len(word) > 2 and (token.startswith(word) or word.startswith(token)) for word in hay.split()
    )


def _target_fit(
    persona: Persona,
    target_text: str,
    topics: list[str],
    affinity: float,
    cfg: SimulationConfig | None = None,
) -> float:
    if "adjacent" in persona.role.lower():
        return 0.0
    hay = f"{persona.role} {' '.join(persona.interests)}".lower()
    needles: list[str] = []
    for part in (target_text, *topics):
        needles.extend(_tokens(part))
    needles = list(dict.fromkeys(needles))
    if not needles:
        return float(affinity)
    hits = sum(1.0 for t in needles if _stem_hit(t, hay))
    overlap = hits / max(3.0, min(len(needles), 10))
    cfg = cfg or DEFAULT_SIM_CONFIG
    return cfg.affinity_overlap_weight * overlap + cfg.affinity_llm_weight * float(affinity)


def heuristic_reactions(personas: list[Persona], features: dict) -> list[PersonaReaction]:
    topics = {t.lower() for t in features.get("topics", [])}
    hook = float(features.get("hook_strength", 0.5))
    clarity = float(features.get("clarity", 0.5))
    novelty = float(features.get("novelty", 0.5))
    promo = float(features.get("promotional_intensity", 0.2))
    controversy = float(features.get("controversy", 0.2))
    visual = float(features.get("visual_hook", 0.0))
    note = str(features.get("media_note", "")).lower()
    has_video = "video" in note or "frames" in note
    has_image = visual > 0.08 or "image" in note
    out: list[PersonaReaction] = []
    for p in personas:
        overlap = len(topics.intersection({i.lower() for i in p.interests}))
        affinity = clamp01(0.25 + 0.2 * overlap + 0.15 * (1 - abs(p.expertise - novelty)))
        like = _sigmoid(
            -1.6
            + 2.0 * affinity
            + 1.0 * hook * p.activity_level
            + 0.6 * clarity
            + 0.35 * visual
            - 2.2 * max(0, promo - p.promotional_tolerance)
        )
        reply = clamp01(like * (0.25 + p.reply_tendency) * (0.5 + p.evidence_demand * controversy))
        repost = clamp01(like * (0.2 + p.repost_tendency) * (0.4 + p.novelty_seeking * novelty))
        quote = clamp01(reply * (0.35 + p.quote_tendency) * (0.5 + controversy))
        share = clamp01(repost * (0.35 + p.share_tendency))
        share_dm = clamp01(share * 0.28 * p.activity_level)
        share_copy = clamp01(share * 0.12 * p.share_tendency)
        dwell = clamp01(0.2 + p.dwell_tendency * (0.4 + hook + 0.3 * visual) / 2)
        click = clamp01(dwell * (0.45 + p.click_tendency) * (0.5 + hook))
        photo = clamp01(click * visual) if has_image else 0.0
        video_open = clamp01(click * (0.4 + visual)) if has_video else 0.0
        open_link = clamp01(click * promo * 0.8)
        follow = clamp01(like * p.follow_tendency * (0.4 + affinity))
        post_unexplored = clamp01(novelty * p.novelty_seeking * 0.35)
        negative = clamp01(
            0.02
            + p.negative_sensitivity * (0.5 * promo + 0.7 * controversy + 0.3 * (1 - clarity))
        )
        not_interested = clamp01(negative * 0.5)
        mute = clamp01(negative * 0.22)
        block = clamp01(negative * 0.16)
        report = clamp01(negative * 0.08 * (0.4 + controversy + p.negative_sensitivity))
        not_dwelled = clamp01((1.0 - dwell) * 0.45)
        reason = (
            f"Affinity {affinity:.2f} vs promo {promo:.2f}. "
            + ("Hook lands." if hook >= 0.6 else "Opening is weak.")
        )
        out.append(
            PersonaReaction(
                persona_id=p.id,
                topic_affinity=round(affinity, 3),
                like_probability=round(like, 3),
                reply_probability=round(reply, 3),
                repost_probability=round(repost, 3),
                quote_probability=round(quote, 3),
                share_probability=round(share, 3),
                share_via_dm_probability=round(share_dm, 3),
                share_via_copy_link_probability=round(share_copy, 3),
                dwell_probability=round(dwell, 3),
                dwell_time=round(dwell * 10.0, 3),
                click_probability=round(click, 3),
                photo_expand_probability=round(photo, 3),
                video_open_probability=round(video_open, 3),
                open_link_probability=round(open_link, 3),
                quoted_click_probability=round(quote * click, 3),
                follow_probability=round(follow, 3),
                post_unexplored_probability=round(post_unexplored, 3),
                not_interested_probability=round(not_interested, 3),
                mute_probability=round(mute, 3),
                block_probability=round(block, 3),
                report_probability=round(report, 3),
                not_dwelled_probability=round(not_dwelled, 3),
                negative_feedback_probability=round(negative, 3),
                reason=reason,
            )
        )
    return out


def _union_probability(values: list[float]) -> float:
    keep = 1.0
    for value in values:
        keep *= 1.0 - clamp01(value)
    return clamp01(1.0 - keep)


def _draw_probability(p: float, rng: np.random.Generator, sigma: float) -> bool:
    p = clamp01(p)
    if p <= 0.0:
        return False
    if p >= 1.0:
        return True
    logit = math.log(p / (1.0 - p))
    noisy = _sigmoid(logit + float(rng.normal(0.0, sigma)))
    return bool(rng.random() < noisy)


def _sample_actions(
    reaction: PersonaReaction,
    rng: np.random.Generator,
    *,
    config: SimulationConfig | None = None,
) -> tuple[set[str], Action]:
    """Sample compatible events while retaining one primary graph label."""

    config = config or DEFAULT_SIM_CONFIG
    sigma = max(0.0, config.action_noise_sigma)
    events: set[str] = set()

    if _draw_probability(reaction.dwell_probability, rng, sigma):
        events.add("dwell")
    if reaction.click_probability > 0.0:
        conditional_click = clamp01(
            reaction.click_probability / max(reaction.dwell_probability, reaction.click_probability, 1e-9)
        )
        if "dwell" in events and _draw_probability(conditional_click, rng, sigma):
            events.add("click")

    for event, probability in (
        ("like", reaction.like_probability),
        ("reply", reaction.reply_probability),
        ("repost", reaction.repost_probability),
        ("quote", reaction.quote_probability),
        (
            "share",
            _union_probability(
                [
                    reaction.share_probability,
                    reaction.share_via_dm_probability,
                    reaction.share_via_copy_link_probability,
                ]
            ),
        ),
        ("follow", reaction.follow_probability),
    ):
        if _draw_probability(probability, rng, sigma):
            events.add(event)

    negative = max(
        clamp01(reaction.negative_feedback_probability),
        _union_probability(
            [
                reaction.not_interested_probability,
                reaction.mute_probability,
                reaction.block_probability,
                reaction.report_probability,
            ]
        ),
    )
    if _draw_probability(negative, rng, sigma):
        events.add("negative")

    for preferred in ("negative", "share", "quote", "repost", "reply", "follow", "like"):
        if preferred in events:
            return events, preferred  # type: ignore[return-value]
    return events, "ignore"


def _jitter(r: PersonaReaction, rng: np.random.Generator, cfg: SimulationConfig | None = None) -> PersonaReaction:
    cfg = cfg or DEFAULT_SIM_CONFIG

    def j(p: float) -> float:
        p = clamp01(p)
        if p <= 0.0 or p >= 1.0 or cfg.jitter_sigma <= 0.0:
            return p
        logit = math.log(p / (1.0 - p))
        return round(_sigmoid(logit + float(rng.normal(0.0, cfg.jitter_sigma))), 6)

    update = {field: j(getattr(r, field)) for field in PROB_FIELDS}
    update["dwell_time"] = round(max(0.0, r.dwell_time + float(rng.normal(0, cfg.dwell_jitter_sigma))), 3)
    return r.model_copy(update=update)


def _personalize_reaction(
    reaction: PersonaReaction,
    engagement_multiplier: float,
    skepticism_multiplier: float,
) -> PersonaReaction:
    """Apply correlated member-level behavior latents to calibrated probabilities."""

    update: dict[str, float] = {}
    for field in PROB_FIELDS:
        multiplier = skepticism_multiplier if field in NEGATIVE_PROB_FIELDS else engagement_multiplier
        update[field] = round(clamp01(float(getattr(reaction, field)) * multiplier), 6)
    update["dwell_time"] = round(max(0.0, reaction.dwell_time * engagement_multiplier), 3)
    return reaction.model_copy(update=update)


SHARE_ACTIONS = {"repost", "quote", "share"}


def _counts(actions: list[set[str]]) -> dict[str, int]:
    out = {a: 0 for a in (*ACTIONS, "dwell", "click")}
    for item in actions:
        if not item:
            out["ignore"] += 1
        for event in item:
            if event in out:
                out[event] += 1
    return out


def _round_result(
    n: int,
    shown: list[set[str]],
    fresh: list[set[str]],
    score: float,
    stopped: bool,
    reason: str | None,
    stage: str = "seed",
) -> RoundResult:
    counts = _counts(fresh)
    return RoundResult(
        round=n,
        audience_size=len(shown),
        likes=counts["like"],
        replies=counts["reply"],
        reposts=counts["repost"],
        quotes=counts["quote"],
        shares=counts["share"],
        follows=counts["follow"],
        negatives=counts["negative"],
        ignores=counts["ignore"],
        dwells=counts["dwell"],
        clicks=counts["click"],
        score=score,
        stopped=stopped,
        stop_reason=reason,
        stage=stage,
    )


def _stage_for_round(n: int) -> str:
    if n <= 1:
        return "seed"
    if n == 2:
        return "adjacent"
    if n == 3:
        return "niche"
    return "general"


def _stage_in_pref(stage: str, cfg: SimulationConfig) -> float:
    if stage == "adjacent":
        return cfg.adjacent_in_pref
    if stage == "niche":
        return cfg.niche_in_pref
    if stage == "general":
        return cfg.general_in_pref
    return cfg.share_target_preference


def graph_run(
    reactions: list[PersonaReaction],
    rng: np.random.Generator,
    population: int,
    boost: int,
    max_rounds: int,
    personas: list[Persona] | None = None,
    target_text: str = "",
    topics: list[str] | None = None,
    overlays: list[Persona] | None = None,
    cfg: SimulationConfig | None = None,
    sample_reactions: list[PersonaReaction] | None = None,
    population_members: list["PopulationMember"] | None = None,
) -> tuple[list[RoundResult], SpreadGraph]:
    cfg = cfg or DEFAULT_SIM_CONFIG
    by_id = {r.persona_id: r for r in reactions}
    # ``sample_reactions`` is retained for replay compatibility with v0.3 reports.
    # All stochastic actions intentionally use the same calibrated reactions as scoring.
    _ = sample_reactions
    roster = personas or [
        Persona(
            id=r.persona_id,
            name=r.persona_id.replace("_", " "),
            role="persona",
            interests=[],
            expertise=0.5,
            activity_level=0.5,
            novelty_seeking=0.5,
            promotional_tolerance=0.5,
            reply_tendency=0.2,
            repost_tendency=0.2,
            dwell_tendency=0.5,
            negative_sensitivity=0.3,
            evidence_demand=0.5,
        )
        for r in reactions
    ]
    if not roster or not reactions:
        return [], SpreadGraph()

    n_pop = int(np.clip(population, cfg.min_population, cfg.max_population))
    if population_members is not None and len(population_members) != n_pop:
        raise ValueError("population_members must contain exactly population members")
    n_boost = int(np.clip(boost, 1, min(12, n_pop)))
    lookup = {p.id: p for p in roster}
    fallback = roster[0]

    slots: list[dict] = []
    n_types = max(1, len(roster))
    for i in range(n_pop):
        member = population_members[i] if population_members is not None else None
        persona = member.behavior.persona if member is not None else roster[i % n_types]
        base = by_id.get(persona.id) or reactions[i % len(reactions)]
        if member is not None:
            personalized = _personalize_reaction(
                base,
                member.behavior.engagement_multiplier,
                member.behavior.skepticism_multiplier,
            )
            member_persona = member.as_persona()
            name = member.display.name
            role = member.display.role
            interests = list(member.display.interests)
            behavior_profile_id = member.behavior.id
            persona_source = member.provenance.source
        else:
            personalized = base
            member_persona = persona
            name = persona.name
            role = persona.role
            interests = list(persona.interests)
            behavior_profile_id = persona.id
            persona_source = "legacy-pack"
        sample_jittered = _jitter(personalized, rng, cfg)
        copy = i // n_types + 1
        if member is None and copy > 1 and overlays:
            ov = overlays[i % len(overlays)]
            name = ov.name
            role = ov.role[:80]
            interests = list(ov.interests)
            persona_source = "legacy-overlay"
        elif member is None and copy > 1:
            name = f"{persona.name} {copy}"
        slots.append(
            {
                "id": member.stable_id if member is not None else f"A{i + 1:02d}",
                "persona": persona,
                "trait_persona": member_persona,
                "name": name,
                "role": role,
                "interests": interests,
                "reaction": personalized,
                "sample_reaction": sample_jittered,
                "shown_round": None,
                "action": "ignore",
                "actions": set(),
                "cohort": "never_shown",
                "in_network": False,
                "ranking_position": None,
                "ranking_selected": None,
                "behavior_profile_id": behavior_profile_id,
                "persona_source": persona_source,
            }
        )

    type_fit = {
        p.id: _target_fit(
            p,
            target_text,
            list(topics or []),
            float((by_id.get(p.id) or reactions[0]).topic_affinity),
            cfg,
        )
        for p in roster
    }
    unique_fits = np.array(list(type_fit.values())) if type_fit else np.array([0.0])
    cutoff = float(np.percentile(unique_fits, cfg.target_fit_cutoff_percentile))
    in_ids = {
        pid
        for pid, fit in type_fit.items()
        if fit >= cutoff and fit > 0.0 and "adjacent" not in lookup[pid].role.lower()
    }
    if len(in_ids) >= n_types:
        worst = sorted(type_fit, key=type_fit.get)[: max(1, n_types // 3)]
        in_ids -= set(worst)
    if not in_ids:
        in_ids = {max(type_fit, key=type_fit.get)}
    for slot in slots:
        slot["in_target"] = slot["persona"].id in in_ids
        follow_rate = (
            cfg.in_network_target_rate if slot["in_target"] else cfg.in_network_out_of_target_rate
        )
        # Synthetic author-follow relationship used only to exercise the public
        # in-network/out-of-network score branches. It is an explicit scenario prior.
        slot["follows_origin"] = bool(rng.random() < clamp01(follow_rate))

    in_q = [i for i in range(n_pop) if slots[i]["in_target"]]
    out_q = [i for i in range(n_pop) if not slots[i]["in_target"]]
    rng.shuffle(in_q)
    rng.shuffle(out_q)
    shown_types: dict[str, int] = {}

    def take(prefer_in: bool) -> int | None:
        primary, secondary = (in_q, out_q) if prefer_in else (out_q, in_q)

        def pick(queue: list[int]) -> int | None:
            if not queue:
                return None
            best_i = 0
            best_c = 10**9
            for i, idx in enumerate(queue):
                count = shown_types.get(slots[idx]["persona"].id, 0)
                if count < best_c:
                    best_c = count
                    best_i = i
                    if count == 0:
                        break
            return queue.pop(best_i)

        idx = pick(primary)
        if idx is None:
            idx = pick(secondary)
        if idx is not None:
            pid = slots[idx]["persona"].id
            shown_types[pid] = shown_types.get(pid, 0) + 1
        return idx

    shown: list[int] = []
    edges: list[SpreadEdge] = []
    rounds: list[RoundResult] = []

    def reveal(
        idx: int,
        round_n: int,
        source: str,
        kind: str,
        *,
        in_network: bool,
        decision: RankingDecision | None = None,
    ) -> None:
        slot = slots[idx]
        slot["shown_round"] = round_n
        slot["cohort"] = "in_target" if slot["in_target"] else "out_of_target"
        events, primary = _sample_actions(slot["sample_reaction"], rng, config=cfg)
        slot["actions"] = events
        slot["action"] = primary
        slot["in_network"] = in_network
        if decision is not None:
            slot["ranking_position"] = decision.rank
            slot["ranking_selected"] = decision.selected
        edges.append(SpreadEdge(source=source, target=slot["id"], kind=kind, round=round_n))
        shown.append(idx)

    def shown_score() -> float:
        if not shown:
            return 0.0
        raw = [
            ranking_score([slots[i]["reaction"]], in_network=bool(slots[i]["in_network"]))
            for i in shown
        ]
        return to_ui_score(sum(raw) / len(raw))

    def remove_from_queue(idx: int) -> None:
        for queue in (in_q, out_q):
            if idx in queue:
                queue.remove(idx)
                break
        pid = slots[idx]["persona"].id
        shown_types[pid] = shown_types.get(pid, 0) + 1

    n_out = max(1, min(n_boost - 1, int(round(n_boost * cfg.out_of_target_seed_frac)))) if n_boost > 1 else 0
    n_in = n_boost - n_out
    fresh: list[int] = []
    for prefer_in, count in ((True, n_in), (False, n_out)):
        for _ in range(count):
            idx = take(prefer_in)
            if idx is None:
                break
            reveal(idx, 1, "POST", "algo", in_network=bool(slots[idx]["follows_origin"]))
            fresh.append(idx)
    score = shown_score()
    rounds.append(
        _round_result(
            1,
            [slots[i]["actions"] for i in shown],
            [slots[i]["actions"] for i in fresh],
            score,
            False,
            None,
            "seed",
        )
    )

    stopped = False
    for n in range(2, max_rounds + 1):
        if not in_q and not out_q:
            break
        stage = _stage_for_round(n)
        prior = len(shown)
        fresh = []
        sharers = [i for i in shown if SHARE_ACTIONS.intersection(slots[i]["actions"])]
        share_pref = _stage_in_pref(stage, cfg)
        for src in sharers:
            fanout = int(rng.integers(cfg.share_fanout_min, cfg.share_fanout_max + 1))
            for _ in range(fanout):
                idx = take(prefer_in=bool(rng.random() < share_pref))
                if idx is None:
                    break
                reveal(
                    idx,
                    n,
                    slots[src]["id"],
                    "share",
                    in_network=bool(slots[idx]["follows_origin"]),
                )
                fresh.append(idx)
        remaining = len(in_q) + len(out_q)
        algo_n = min(remaining, max(2, int(cfg.algo_exposure_rate * n_pop)))
        parents = shown[:] or [0]
        stage_pref = _stage_in_pref(stage, cfg)
        # Pull the stage preference toward the target audience by the configured
        # algorithmic preference; 0 leaves the stage mix unchanged, 1 is all target.
        algo_pref = clamp01(stage_pref + cfg.algo_target_preference * (1.0 - stage_pref))
        ranked: list[tuple[int, RankingDecision, int]] = []
        for idx in (*in_q, *out_q):
            candidate_in_network = bool(slots[idx]["follows_origin"])
            decision = rank_target(
                slots[idx]["sample_reaction"],
                rng,
                in_network=candidate_in_network,
                stage=stage,
                config=cfg,
            )
            if not decision.selected:
                continue
            preferred = slots[idx]["in_target"] == bool(rng.random() < algo_pref)
            ranked.append((0 if preferred else 1, decision, idx))
        ranked.sort(key=lambda row: (row[0], row[1].rank, -row[1].target_score, row[2]))
        for _, decision, idx in ranked[:algo_n]:
            remove_from_queue(idx)
            parent = slots[int(rng.choice(parents))]
            reveal(
                idx,
                n,
                parent["id"],
                "algo",
                in_network=bool(slots[idx]["follows_origin"]),
                decision=decision,
            )
            fresh.append(idx)
        score = shown_score()
        new = len(shown) - prior
        velocity = new / max(1, prior)
        neg_frac = sum(1 for i in shown if slots[i]["action"] == "negative") / max(1, len(shown))
        stopped = False
        reason = None
        if neg_frac >= cfg.negative_stop_rate and n >= 2:
            stopped = True
            reason = f"negative-signal stop at round {n}."
        elif velocity < cfg.velocity_stop_threshold and n >= cfg.velocity_stop_min_round:
            stopped = True
            reason = f"stalled at round {n} — velocity < {cfg.velocity_stop_threshold:.0%}."
        rounds.append(
            _round_result(
                n,
                [slots[i]["actions"] for i in shown],
                [slots[i]["actions"] for i in fresh],
                score,
                stopped,
                reason,
                stage,
            )
        )
        if stopped:
            break

    agents = [
        SpreadAgent(
            id="POST",
            persona_id="post",
            name="Post",
            role="Origin",
            interests=[],
            cohort="origin",
            shown_round=0,
            action="ignore",
            watched=1.0,
            reason="Seed post.",
            skepticism=0.0,
            share_tendency=1.0,
        )
    ]
    for slot in slots:
        persona = slot["persona"]
        reaction: PersonaReaction = slot["reaction"]
        pack = slot.get("trait_persona") or lookup.get(persona.id, fallback)
        agents.append(
            SpreadAgent(
                id=slot["id"],
                persona_id=persona.id,
                name=slot.get("name", persona.name),
                role=slot.get("role", persona.role),
                interests=list(slot.get("interests", persona.interests)),
                cohort=slot["cohort"],
                in_target=bool(slot["in_target"]),
                shown_round=slot["shown_round"],
                action=slot["action"],
                actions=sorted(slot["actions"]),
                in_network=bool(slot["in_network"]),
                ranking_position=slot["ranking_position"],
                ranking_selected=slot["ranking_selected"],
                behavior_profile_id=slot["behavior_profile_id"],
                persona_source=slot["persona_source"],
                watched=round(float(reaction.dwell_probability), 3),
                reason=reaction.reason,
                skepticism=round(clamp01(float(pack.negative_sensitivity) + float(rng.normal(0, 0.05))), 3),
                share_tendency=round(clamp01(float(pack.repost_tendency) + float(rng.normal(0, 0.06))), 3),
            )
        )
    return rounds, SpreadGraph(agents=agents, edges=edges)


def _exposure_pct(graph: SpreadGraph) -> float:
    people = [a for a in graph.agents if a.cohort != "origin"]
    shown = [a for a in people if a.cohort != "never_shown"]
    if not people:
        return 0.0
    return 100.0 * len(shown) / len(people)


def simulate(
    reactions: list[PersonaReaction],
    seed: int,
    users_per_persona: int,
    runs: int,
    max_rounds: int,
    personas: list[Persona] | None = None,
    population: int | None = None,
    boost: int = 6,
    target_text: str = "",
    topics: list[str] | None = None,
    overlays: list[Persona] | None = None,
    cfg: SimulationConfig | None = None,
    config: SimulationConfig | None = None,
    sample_reactions: list[PersonaReaction] | None = None,
    population_members: list["PopulationMember"] | None = None,
) -> SimulationSummary:
    if cfg is not None and config is not None and cfg != config:
        raise ValueError("Pass either cfg or config, not conflicting values for both.")
    cfg = config or cfg or DEFAULT_SIM_CONFIG
    rng = np.random.default_rng(seed)
    n_pop = population or users_per_persona * max(1, len(reactions))
    run_count = max(1, runs)
    scores: list[float] = []
    depths: list[int] = []
    exposures: list[float] = []
    outcomes: list[tuple[list[RoundResult], SpreadGraph, float, int, float]] = []
    for i in range(run_count):
        run_seed = seed if i == 0 else int(rng.integers(0, 1_000_000_000))
        result, run_graph = graph_run(
            reactions,
            np.random.default_rng(run_seed),
            population=n_pop,
            boost=boost,
            max_rounds=max_rounds,
            personas=personas,
            target_text=target_text,
            topics=topics,
            overlays=overlays,
            cfg=cfg,
            sample_reactions=sample_reactions,
            population_members=population_members,
        )
        final_score = result[-1].score if result else 0.0
        scores.append(final_score)
        depths.append(len(result))
        exposure = _exposure_pct(run_graph)
        exposures.append(exposure)
        outcomes.append((result, run_graph, final_score, len(result), exposure))
    arr = np.array(scores) if scores else np.array([0.0])
    median_exposure = float(np.median(exposures)) if exposures else 0.0
    median_score = float(np.median(scores)) if scores else 0.0
    median_depth = float(np.median(depths)) if depths else 0.0
    viz_rounds, graph, _, _, _ = min(
        outcomes,
        key=lambda item: (
            abs(item[4] - median_exposure),
            abs(item[2] - median_score),
            abs(item[3] - median_depth),
        ),
    )
    return SimulationSummary(
        seed=seed,
        runs=run_count,
        rounds=viz_rounds,
        score_p10=round(float(np.percentile(arr, 10)), 1),
        score_p50=round(float(np.percentile(arr, 50)), 1),
        score_p90=round(float(np.percentile(arr, 90)), 1),
        reached_round_p50=round(float(np.median(depths)), 1),
        out_of_network=bool(np.median(depths) >= 3),
        graph=graph,
        exposure_p10=round(float(np.percentile(exposures, 10)), 1) if exposures else 0.0,
        exposure_p50=round(float(np.percentile(exposures, 50)), 1) if exposures else 0.0,
        exposure_p90=round(float(np.percentile(exposures, 90)), 1) if exposures else 0.0,
    )
