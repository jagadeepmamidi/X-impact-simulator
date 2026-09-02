export const NICHES = ["tech", "fitness", "finance", "comedy"] as const;
export type Niche = (typeof NICHES)[number];

export const NICHE_COPY: Record<Niche, string> = {
  tech: "Solo founders and small teams running tech businesses",
  fitness: "Gym-goers, coaches, and health-curious scrollers",
  finance: "Retail traders, allocators, and personal-finance readers",
  comedy: "Joke accounts, satire readers, and casual scrollers",
};

export type PersonaReaction = {
  persona_id: string;
  topic_affinity: number;
  like_probability: number;
  reply_probability: number;
  repost_probability: number;
  quote_probability?: number;
  share_probability?: number;
  dwell_probability: number;
  follow_probability: number;
  negative_feedback_probability: number;
  report_probability?: number;
  reason: string;
};

export type RoundResult = {
  round: number;
  audience_size: number;
  likes: number;
  replies: number;
  reposts: number;
  quotes?: number;
  shares?: number;
  follows: number;
  negatives: number;
  ignores: number;
  score: number;
  stopped: boolean;
  stop_reason: string | null;
  stage?: string;
};

export type SpreadAction =
  | "ignore"
  | "like"
  | "reply"
  | "repost"
  | "quote"
  | "share"
  | "follow"
  | "negative";

export type SpreadCohort = "origin" | "in_target" | "out_of_target" | "never_shown";

export type SpreadAgent = {
  id: string;
  persona_id: string;
  name: string;
  role: string;
  interests: string[];
  cohort: SpreadCohort;
  in_target?: boolean;
  shown_round: number | null;
  action: SpreadAction;
  watched: number;
  reason: string;
  skepticism: number;
  share_tendency: number;
};

export type SpreadEdge = {
  source: string;
  target: string;
  kind: "share" | "algo";
  round: number;
};

export type SpreadGraph = {
  agents: SpreadAgent[];
  edges: SpreadEdge[];
};

export type ImpactReport = {
  experimental: boolean;
  disclaimer: string;
  niche: Niche;
  groq_used: boolean;
  heads_used?: boolean;
  impact_score: number;
  weights_note: string;
  content: {
    topics: string[];
    format: string;
    hook_strength: number;
    clarity: number;
    novelty: number;
    controversy: number;
    promotional_intensity: number;
    safety_risk: number;
    visual_hook: number;
    media_note: string;
    source: string;
  };
  reactions: PersonaReaction[];
  simulation: {
    seed: number;
    runs: number;
    rounds: RoundResult[];
    score_p10: number;
    score_p50: number;
    score_p90: number;
    reached_round_p50: number;
    out_of_network: boolean;
    graph?: SpreadGraph;
    exposure_p10?: number;
    exposure_p50?: number;
    exposure_p90?: number;
  };
  explanation: {
    headline: string;
    summary: string;
    suggestions: string[];
    source: string;
  };
  run_id?: string | null;
  audience_fit?: number;
  niche_index?: number;
  negative_signal_risk?: number;
  stability?: number;
  confidence?: number;
  reach_pct?: number;
  heads_note?: string;
  inference_path?: string;
  simulator_version?: string;
  calibration_version?: string;
  config_version?: string;
  prompt_version?: string;
  input_text?: string;
  population?: number;
  boost?: number;
  llm_model?: string;
  parent_run_id?: string | null;
  distribution_potential?: number;
  engagement_quality?: number;
  profile_impact?: number;
  stop_reason?: string;
};

export type OutcomeRecord = {
  run_id: string;
  impressions?: number | null;
  likes?: number | null;
  replies?: number | null;
  reposts?: number | null;
  follows?: number | null;
  note?: string;
};

export type CompareReport = {
  a: ImpactReport;
  b: ImpactReport;
  delta: {
    impact_score: number;
    niche_index: number;
    audience_fit: number;
    reach_pct: number;
    confidence: number;
    distribution_potential?: number;
    engagement_quality?: number;
    profile_impact?: number;
  };
};
