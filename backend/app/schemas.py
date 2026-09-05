from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Niche = Literal["tech", "fitness", "finance", "comedy"]
Action = Literal[
    "ignore",
    "like",
    "reply",
    "repost",
    "quote",
    "share",
    "follow",
    "negative",
]
InteractionEvent = Literal[
    "dwell",
    "click",
    "like",
    "reply",
    "repost",
    "quote",
    "share",
    "follow",
    "negative",
    "ignore",
]


class ContentFeatures(BaseModel):
    topics: list[str] = Field(default_factory=list)
    format: str = "other"
    sentiment: str = "neutral"
    hook_strength: float = Field(ge=0, le=1, default=0.5)
    clarity: float = Field(ge=0, le=1, default=0.5)
    novelty: float = Field(ge=0, le=1, default=0.5)
    controversy: float = Field(ge=0, le=1, default=0.2)
    promotional_intensity: float = Field(ge=0, le=1, default=0.2)
    safety_risk: float = Field(ge=0, le=1, default=0.05)
    visual_hook: float = Field(ge=0, le=1, default=0.0)
    transcript_excerpt: str = ""
    source: Literal["groq", "heuristic"] = "heuristic"
    media_note: str = "Text-only analysis."


class Persona(BaseModel):
    id: str
    name: str
    role: str
    interests: list[str]
    expertise: float = Field(ge=0, le=1)
    activity_level: float = Field(ge=0, le=1)
    novelty_seeking: float = Field(ge=0, le=1)
    promotional_tolerance: float = Field(ge=0, le=1)
    reply_tendency: float = Field(ge=0, le=1)
    repost_tendency: float = Field(ge=0, le=1)
    quote_tendency: float = Field(default=0.12, ge=0, le=1)
    share_tendency: float = Field(default=0.18, ge=0, le=1)
    click_tendency: float = Field(default=0.4, ge=0, le=1)
    follow_tendency: float = Field(default=0.06, ge=0, le=1)
    dwell_tendency: float = Field(ge=0, le=1)
    negative_sensitivity: float = Field(ge=0, le=1)
    evidence_demand: float = Field(ge=0, le=1)


class PersonaReaction(BaseModel):
    persona_id: str
    topic_affinity: float = Field(ge=0, le=1)
    like_probability: float = Field(ge=0, le=1)
    reply_probability: float = Field(ge=0, le=1)
    repost_probability: float = Field(ge=0, le=1)
    quote_probability: float = Field(default=0.0, ge=0, le=1)
    share_probability: float = Field(default=0.0, ge=0, le=1)
    share_via_dm_probability: float = Field(default=0.0, ge=0, le=1)
    share_via_copy_link_probability: float = Field(default=0.0, ge=0, le=1)
    dwell_probability: float = Field(ge=0, le=1)
    dwell_time: float = Field(default=0.0, ge=0)
    click_probability: float = Field(default=0.0, ge=0, le=1)
    photo_expand_probability: float = Field(default=0.0, ge=0, le=1)
    video_open_probability: float = Field(default=0.0, ge=0, le=1)
    open_link_probability: float = Field(default=0.0, ge=0, le=1)
    quoted_click_probability: float = Field(default=0.0, ge=0, le=1)
    follow_probability: float = Field(ge=0, le=1)
    post_unexplored_probability: float = Field(default=0.0, ge=0, le=1)
    not_interested_probability: float = Field(default=0.0, ge=0, le=1)
    mute_probability: float = Field(default=0.0, ge=0, le=1)
    block_probability: float = Field(default=0.0, ge=0, le=1)
    report_probability: float = Field(default=0.0, ge=0, le=1)
    not_dwelled_probability: float = Field(default=0.0, ge=0, le=1)
    negative_feedback_probability: float = Field(ge=0, le=1)
    reason: str = Field(max_length=2_000)


class RoundResult(BaseModel):
    round: int
    audience_size: int
    likes: int
    replies: int
    reposts: int
    quotes: int = 0
    shares: int = 0
    clicks: int = 0
    dwells: int = 0
    follows: int
    negatives: int
    ignores: int
    score: float
    stopped: bool = False
    stop_reason: str | None = None
    stage: str = "seed"


Cohort = Literal["origin", "in_target", "out_of_target", "never_shown"]
EdgeKind = Literal["share", "algo"]


class SpreadAgent(BaseModel):
    id: str
    persona_id: str
    behavior_profile_id: str = ""
    persona_source: str = ""
    name: str
    role: str
    interests: list[str] = Field(default_factory=list)
    cohort: Cohort
    in_target: bool = False
    shown_round: int | None = None
    action: Action = "ignore"
    actions: list[InteractionEvent] = Field(default_factory=list)
    watched: float = Field(default=0.0, ge=0, le=1)
    reason: str = ""
    skepticism: float = Field(default=0.0, ge=0, le=1)
    share_tendency: float = Field(default=0.0, ge=0, le=1)
    in_network: bool = False
    ranking_position: int | None = Field(default=None, ge=1)
    ranking_selected: bool | None = None


class SpreadEdge(BaseModel):
    source: str
    target: str
    kind: EdgeKind
    round: int


class SpreadGraph(BaseModel):
    agents: list[SpreadAgent] = Field(default_factory=list)
    edges: list[SpreadEdge] = Field(default_factory=list)


class SimulationSummary(BaseModel):
    seed: int
    runs: int
    rounds: list[RoundResult]
    score_p10: float
    score_p50: float
    score_p90: float
    reached_round_p50: float
    out_of_network: bool
    graph: SpreadGraph = Field(default_factory=SpreadGraph)
    exposure_p10: float = 0.0
    exposure_p50: float = 0.0
    exposure_p90: float = 0.0


class Explanation(BaseModel):
    headline: str
    summary: str
    suggestions: list[str]
    source: Literal["groq", "heuristic"] = "heuristic"


class ImpactReport(BaseModel):
    experimental: bool = True
    disclaimer: str
    niche: Niche
    groq_used: bool
    content: ContentFeatures
    reactions: list[PersonaReaction]
    simulation: SimulationSummary
    impact_score: float
    explanation: Explanation
    weights_note: str
    heads_used: bool = False
    heads_note: str = ""
    run_id: str | None = None
    audience_fit: float = 0.0
    niche_index: float = 0.0
    negative_signal_risk: float = 0.0
    stability: float = 0.0
    confidence: float = 0.0
    reach_pct: float = 0.0
    inference_path: str = "heuristic"
    simulator_version: str = ""
    calibration_version: str = ""
    config_version: str = ""
    prompt_version: str = ""
    input_text: str = ""
    population: int = 100
    boost: int = 6
    llm_model: str = ""
    parent_run_id: str | None = None
    affinity_reactions: list[PersonaReaction] = Field(default_factory=list)
    distribution_potential: float = 0.0
    engagement_quality: float = 0.0
    profile_impact: float = 50.0
    stop_reason: str = ""
    probability_semantics: str = "legacy-unspecified"
    calibration_status: str = "unknown"
    data_coverage_status: str = "unknown"
    uncertainty_note: str = ""
    fallback_reasons: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    persona_pack_version: str = ""
    persona_pack_hash: str = ""
    dataset_revision: str = ""
    dataset_hash: str = ""
    action_model_version: str = ""
    action_model_hash: str = ""
    weights_version: str = ""
    weights_hash: str = ""
    input_hash: str = ""
    snapshot_hash: str = ""
    replay_contract_version: str = "replay-v3"
    replay_mode: Literal["original", "exact", "seed-variant", "legacy-approximate"] = "original"
    replayable: bool = False
    replay_limitations: list[str] = Field(default_factory=list)


class CompareDelta(BaseModel):
    impact_score: float
    niche_index: float
    audience_fit: float
    reach_pct: float
    confidence: float
    distribution_potential: float = 0.0
    engagement_quality: float = 0.0
    profile_impact: float = 0.0


class OutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    run_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    impressions: float | None = Field(default=None, ge=0)
    likes: float | None = Field(default=None, ge=0)
    replies: float | None = Field(default=None, ge=0)
    reposts: float | None = Field(default=None, ge=0)
    quotes: float | None = Field(default=None, ge=0)
    shares: float | None = Field(default=None, ge=0)
    follows: float | None = Field(default=None, ge=0)
    profile_clicks: float | None = Field(default=None, ge=0)
    link_clicks: float | None = Field(default=None, ge=0)
    video_views: float | None = Field(default=None, ge=0)
    watch_time_seconds: float | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
    observation_window_hours: float | None = Field(default=None, gt=0, le=8_760)
    data_source: Literal["manual", "x_analytics_export", "api"] = "manual"
    note: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def validate_observation(self) -> "OutcomeRecord":
        count_fields = (
            "likes",
            "replies",
            "reposts",
            "quotes",
            "shares",
            "follows",
            "profile_clicks",
            "link_clicks",
        )
        bounded_values = [getattr(self, name) for name in count_fields]
        observed_values = [*bounded_values, self.video_views]
        if self.impressions is None and any(value is not None for value in observed_values):
            raise ValueError("impressions is required when action outcomes are supplied")
        if self.impressions is None and self.watch_time_seconds is None:
            raise ValueError("record at least impressions or watch_time_seconds")
        if self.impressions is not None:
            for name, value in zip(count_fields, bounded_values, strict=True):
                if value is not None and value > self.impressions:
                    raise ValueError(f"{name} cannot exceed impressions")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return self


class CompareReport(BaseModel):
    a: ImpactReport
    b: ImpactReport
    delta: CompareDelta
