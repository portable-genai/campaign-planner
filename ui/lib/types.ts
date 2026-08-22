/**
 * Domain shapes mirrored from the D2 FastAPI backend (the JSON shape of a cited Plan
 * produced by `to_jsonable`).
 */

export type Market = "JP" | "AU" | "SG";
export type Vertical = "banking" | "online_retail";
export type Pacing = "even" | "front_loaded" | "back_loaded";

export interface Citation {
  source_id: string;
  source_type: string;
  title: string;
  url?: string;
  page?: number | null;
  published_date?: string | null;
  snippet?: string;
  score?: number | null;
}

export interface AudienceSegment {
  id: string;
  name: string;
  size: number;
  reachable_size: number;
  propensity: number;
  expected_value: number;
  consent_rate: number;
  consented_reachable: number;
  tags: string[];
}

export interface SelectedSegment {
  segment: AudienceSegment;
  score: number;
  rank: number;
  rationale?: string;
  citations: Citation[];
}

export interface BudgetLine {
  channel: string;
  amount: number;
  share: number;
  expected_impressions: number;
  expected_reach: number;
  expected_conversions: number;
  expected_cost_per_conversion: number | null;
  citations: Citation[];
}

export interface ChannelMix {
  market: Market;
  vertical: Vertical;
  total_budget: number;
  lines: BudgetLine[];
  allocated: number;
  expected_conversions: number;
  expected_reach: number;
  blended_cost_per_conversion: number | null;
  requires_human_review: boolean;
}

export interface ReachFrequency {
  market: Market;
  vertical: Vertical;
  impressions: number;
  unique_reach: number;
  addressable: number;
  average_frequency: number;
  effective_reach: number;
  effective_frequency: number;
  rationale?: string;
  reach_pct: number;
}

export interface FlightLeg {
  index: number;
  start_date: string;
  end_date: string;
  weight: number;
  amount: number;
}

export interface FlightSchedule {
  market: Market;
  vertical: Vertical;
  start_date: string;
  end_date: string;
  strategy: string;
  total_budget: number;
  legs: FlightLeg[];
  paced_total: number;
}

export interface Plan {
  id: string;
  objective: string;
  market: Market;
  vertical: Vertical;
  total_budget: number;
  segments: SelectedSegment[];
  channel_mix: ChannelMix;
  reach_frequency: ReachFrequency;
  flight_schedule: FlightSchedule;
  creative_brief: string;
  summary: string;
  citations: Citation[];
  requires_human_review: boolean;
}

export interface Health {
  status: string;
  profile: string;
  market: string;
  vertical: string;
}

/** A seeded dev persona (local profile only; see GET /v1/personas). */
export interface Persona {
  id: string;
  subject: string;
  tenant: string;
  principals: string;
}
