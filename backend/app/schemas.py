from typing import Literal

from pydantic import BaseModel, Field

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
    expertise: float
    activity_level: float
    novelty_seeking: float
    promotional_tolerance: float
    reply_tendency: float
    repost_tendency: float
    quote_tendency: float = 0.12
    share_tendency: float = 0.18
    click_tendency: float = 0.4
    follow_tendency: float = 0.06
    dwell_tendency: float
    negative_sensitivity: float
    evidence_demand: float


class PersonaReaction(BaseModel):
    persona_id: str
    topic_affinity: float
    like_probability: float
    reply_probability: float
    repost_probability: float
    quote_probability: float = 0.0
    share_probability: float = 0.0
    share_via_dm_probability: float = 0.0
    share_via_copy_link_probability: float = 0.0
    dwell_probability: float
    dwell_time: float = 0.0
    click_probability: float = 0.0
    photo_expand_probability: float = 0.0
    video_open_probability: float = 0.0
    open_link_probability: float = 0.0
    quoted_click_probability: float = 0.0
    follow_probability: float
    post_unexplored_probability: float = 0.0
    not_interested_probability: float = 0.0
    mute_probability: float = 0.0
    block_probability: float = 0.0
    report_probability: float = 0.0
    not_dwelled_probability: float = 0.0
    negative_feedback_probability: float
    reason: str


class RoundResult(BaseModel):
    round: int
    audience_size: int
    likes: int
    replies: int
    reposts: int
    quotes: int = 0
    shares: int = 0
    follows: int
    negatives: int
    ignores: int
    score: float
    stopped: bool = False
    stop_reason: str | None = None


Cohort = Literal["origin", "in_target", "out_of_target", "never_shown"]
EdgeKind = Literal["share", "algo"]


class SpreadAgent(BaseModel):
    id: str
    persona_id: str
    name: str
    role: str
    interests: list[str] = Field(default_factory=list)
    cohort: Cohort
    in_target: bool = False
    shown_round: int | None = None
    action: Action = "ignore"
    watched: float = 0.0
    reason: str = ""
    skepticism: float = 0.0
    share_tendency: float = 0.0


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


class CompareDelta(BaseModel):
    impact_score: float
    niche_index: float
    audience_fit: float
    reach_pct: float
    confidence: float


class CompareReport(BaseModel):
    a: ImpactReport
    b: ImpactReport
    delta: CompareDelta
