"""Domain models for the Campaign Planning and Budget Allocation system (D2).

This module is the heart of the hexagon. It has **no dependency on Google Cloud,
ADK, FastAPI, or any framework** (only the Python standard library). Every adapter
(GCP, remote-platform, or on-prem placeholder) speaks in terms of these types, which
is what lets the managed-service stack be swapped for an on-premise one without
touching domain logic (no vendor lock-in, ports and adapters).

D2 is deliberately **generic marketing campaign planning**, not a bank-specific tool:

* ``Vertical`` is a configurable enum (banking, online retail), so the same engines
  plan a deposit-account acquisition campaign and an e-commerce seasonal-sale push.
* ``Market`` is a configurable enum (JP, AU, SG) carrying its residency region and
  locales, so JP, AU and SG are first-class config and seed, never hard-coded.

The deterministic engines are the heart of the system: audience / segment selection and
propensity use, channel-mix and budget allocation optimisation, reach / frequency
estimation, and pacing / calendar (flight-schedule) building. The LLM only drafts the
creative brief and the plan summary; every claim that leaves the system carries a
:class:`Citation` and every consequential aggregate sets ``requires_human_review``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from agent_eval_kit.report import EvalMetricResult as EvalMetricResult
from agent_eval_kit.report import EvalReport as EvalReport
from hex_service_kit import StrEnum
from hex_service_kit.observability import TokenUsage

from .kernel import ThinkingLevel


def utcnow() -> datetime:
    """Timezone-aware UTC now (the single clock the domain uses)."""
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Vertical and Market — the two configurable axes (generic, multi-vertical, APAC)
# --------------------------------------------------------------------------- #
class Vertical(StrEnum):
    """The business vertical the plan is scoped to.

    D2 is generic: banking is ONE vertical and online retail is another. The
    deterministic engines and the LLM prompts switch taxonomy / rules by vertical; no
    bank-only logic is baked into the domain.
    """

    BANKING = "banking"
    ONLINE_RETAIL = "online_retail"


class Market(StrEnum):
    """A supported market (Japan, Australia, Singapore).

    The residency region, locales and per-market rule sets are config + seed (see
    :data:`MARKET_PROFILES` and ``config/settings.yaml``), never hard-coded into a
    branch. Adding a market is a config + seed change, not a code change.
    """

    JP = "JP"
    AU = "AU"
    SG = "SG"


@dataclass(frozen=True, slots=True)
class MarketProfile:
    """Static, fictional-data-friendly metadata for a market.

    The residency ``region`` is a GCP regional id selectable at deploy and validated;
    ``locales`` drives bilingual (ja + en) output. These defaults can be overridden in
    ``config/settings.yaml`` so the catalog stays config-driven.
    """

    market: Market
    region: str  # GCP residency region, e.g. "asia-northeast1" (Tokyo)
    display_name: str
    locales: tuple[str, ...]  # e.g. ("ja", "en") or ("en",)
    currency: str = ""


# Built-in defaults. Region/locale are config + seed: settings.yaml may override these.
MARKET_PROFILES: dict[Market, MarketProfile] = {
    Market.JP: MarketProfile(
        market=Market.JP,
        region="asia-northeast1",
        display_name="Japan",
        locales=("ja", "en"),
        currency="JPY",
    ),
    Market.AU: MarketProfile(
        market=Market.AU,
        region="australia-southeast1",
        display_name="Australia",
        locales=("en",),
        currency="AUD",
    ),
    Market.SG: MarketProfile(
        market=Market.SG,
        region="asia-southeast1",
        display_name="Singapore",
        locales=("en",),
        currency="SGD",
    ),
}


# --------------------------------------------------------------------------- #
# Provenance / citation
# --------------------------------------------------------------------------- #
class SourceType(StrEnum):
    """Every citation names which kind of evidence it points to."""

    AUDIENCE_DATA = "audience_data"  # a BigQuery audience / segment table row
    BENCHMARK = "benchmark"  # a channel cost / performance benchmark
    RULE = "rule"  # a per-market / per-vertical planning rule
    POLICY = "policy"  # an internal budgeting / approval policy
    INTERNAL = "internal"  # an internal note / prior plan
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Citation:
    """Provenance attached to every figure and recommendation in a plan.

    A planner must be able to trace every number, segment and channel allocation back to
    its exact source: an auditable campaign plan is the whole point of D2.
    """

    source_id: str
    source_type: SourceType
    title: str
    url: str = ""
    page: int | None = None
    published_date: str | None = None  # ISO date as published, if known
    snippet: str = ""
    score: float | None = None


# --------------------------------------------------------------------------- #
# Generation (LLM) — the LLM only drafts / narrates; never decides the numbers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str  # "user" | "model" | "system"
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    messages: tuple[LlmMessage, ...]
    system_instruction: str | None = None
    model: str | None = None  # None => adapter default from config
    thinking: ThinkingLevel = ThinkingLevel.MEDIUM
    temperature: float = 0.2
    max_output_tokens: int = 4096
    response_schema: dict | None = None  # JSON schema for structured output


# ``TokenUsage`` was declared here: three ``int`` fields defaulting to zero. Sixteen repositories
# had that same declaration, byte-identical, which is a shared value type that had simply never
# been shared. It is now RE-EXPORTED from ``hex_service_kit.observability`` (imported at the top of
# this module) rather than redeclared, so there is one definition to change and no drift class to
# police. ``campaign_planner.domain.models.TokenUsage`` keeps working as an import path.


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    raw: dict | None = None


# --------------------------------------------------------------------------- #
# Safety (guardrail) — A1 Guardrail Gateway concern
# --------------------------------------------------------------------------- #
class GuardrailCategory(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    SENSITIVE_DATA = "sensitive_data"
    MALICIOUS_URL = "malicious_url"
    OTHER = "other"


class Direction(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class GuardrailFinding:
    category: GuardrailCategory
    confidence: str  # "low" | "medium" | "high"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    direction: Direction
    findings: tuple[GuardrailFinding, ...] = ()
    sanitized_text: str | None = None
    reason: str = ""


# --------------------------------------------------------------------------- #
# Audit and observability — A5 Observability, Audit and FinOps concern
# --------------------------------------------------------------------------- #
class Decision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"  # routed to a human (maker-checker)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable, WORM-stored record of one campaign-planning interaction."""

    action: str  # "campaign_plan" | "budget_allocation"
    actor: str  # authenticated planner / service identity
    decision: Decision
    prompt: str = ""
    response: str = ""
    citations: tuple[Citation, ...] = ()
    resource: str = "campaign-planner"
    trace_id: str | None = None
    timestamp: datetime = field(default_factory=utcnow)
    metadata: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Evaluation gate — A4 AI Quality and Model-Risk concern
# --------------------------------------------------------------------------- #
# ``EvalMetricResult`` and ``EvalReport`` were declared here too, and are now RE-EXPORTED from
# ``agent_eval_kit.report`` (imported at the top of this module). The commons ``EvalReport`` is a
# strict SUPERSET: the three fields this repo declared are unchanged, and the additions
# (``run_id``, ``dataset_version``, ``dataset_digest``, ``evaluator``, ``schema_version``,
# ``trace_id``, ``correlation_id``, ``artifact_refs``, ``attested``) all carry defaults, so every
# existing constructor still compiles. Critically the fail-closed ``passed`` rule is IDENTICAL:
# ``n_examples > 0 and bool(results) and all(...)``. ``all(())`` is vacuously True, so a report
# that scored nothing would otherwise certify a promotion, and ``eval/run_eval.py`` exits 0 on
# this property. Re-exporting a WEAKER rule would have been a silent fail-open, which is why the
# rule was compared line by line before the bodies were deleted, and why
# ``tests/unit/test_eval_report_gate.py`` still exercises all four corners of it here.
#
# The submodule import path is deliberate: ``agent_eval_kit`` at package root pulls in the gate
# client and therefore ``httpx``, and this module promises to stay framework-free.


# --------------------------------------------------------------------------- #
# Governance — A3 Agent Registry and the MCP tool catalog
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AgentSkill:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Minimal A2A-style agent card published at /.well-known/agent-card.json."""

    name: str
    description: str
    url: str
    version: str
    skills: tuple[AgentSkill, ...] = ()
    provider: str = "campaign-planner"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A governed, least-privilege tool exposed to the agent (typically via MCP)."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Shared severity scale
# --------------------------------------------------------------------------- #
class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# 1. Audience segments and selection
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AudienceSegment:
    """One addressable audience segment, sourced from the audience-data store.

    ``propensity`` (0..1) is the modelled likelihood the segment responds to the offer;
    ``reachable_size`` is how many of the segment can actually be reached on the planned
    channels. Both come from the audience-data port (BigQuery in the managed stack); the
    selection engine ranks segments by these, never the LLM.
    """

    id: str
    name: str
    market: Market
    vertical: Vertical
    size: int  # total population of the segment
    reachable_size: int  # addressable subset
    propensity: float  # 0..1 modelled response propensity
    expected_value: float  # per-conversion value in market currency
    consent_rate: float = 1.0  # 0..1 fraction with marketing consent (PDPA / APP etc.)
    tags: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()

    @property
    def consented_reachable(self) -> int:
        """Reachable AND consented: the only audience a campaign may actually target."""
        return int(round(self.reachable_size * max(0.0, min(self.consent_rate, 1.0))))


@dataclass(frozen=True, slots=True)
class SelectedSegment:
    """A segment chosen by the selection engine, with its deterministic score."""

    segment: AudienceSegment
    score: float  # 0..1 deterministic (propensity x value x consent), normalised
    rank: int
    rationale: str = ""
    citations: tuple[Citation, ...] = ()


# --------------------------------------------------------------------------- #
# 2. Channels, channel mix and budget allocation
# --------------------------------------------------------------------------- #
class Channel(StrEnum):
    """A media channel a campaign can run on (generic across verticals).

    Per-channel cost and reach assumptions live in the seed / benchmarks, not the enum,
    so the engine stays generic and market / vertical specific via config + seed.
    """

    SEARCH = "search"
    SOCIAL = "social"
    DISPLAY = "display"
    VIDEO = "video"
    EMAIL = "email"
    SMS = "sms"
    PARTNER = "partner"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ChannelBenchmark:
    """Cost / performance assumptions for one channel in a market and vertical.

    Sourced from the audience-data / benchmark store (BigQuery managed; seeded fictional
    data offline). The optimiser uses these; the LLM never sets a CPM or a conversion rate.
    """

    channel: Channel
    market: Market
    vertical: Vertical
    cpm: float  # cost per mille (per 1000 impressions), market currency
    ctr: float  # click-through rate 0..1
    conversion_rate: float  # 0..1 click -> conversion
    max_reach: int  # ceiling on unique reachable people on this channel
    min_spend: float = 0.0  # channel floor (e.g. partner buy minimum)
    citations: tuple[Citation, ...] = ()

    @property
    def cost_per_conversion(self) -> float:
        """Deterministic effective CAC for this channel (0 means non-converting)."""
        per_impression = self.ctr * self.conversion_rate
        if per_impression <= 0:
            return float("inf")
        # cpm is per 1000 impressions; cost per conversion = (cpm / 1000) / per_impression.
        return (self.cpm / 1000.0) / per_impression


@dataclass(frozen=True, slots=True)
class BudgetLine:
    """One line of the allocated budget: how much spend goes to one channel and why.

    Every figure here is deterministic output of the allocation optimiser, with the
    benchmark citations it was derived from.
    """

    channel: Channel
    amount: float  # allocated spend, market currency
    share: float  # 0..1 fraction of the total budget
    expected_impressions: int
    expected_reach: int
    expected_conversions: float
    expected_cost_per_conversion: float
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ChannelMix:
    """The optimised channel mix: budget lines plus the totals they roll up to.

    Consequential output of the budget-allocation optimiser. The mix never auto-executes;
    a human signs off (see :attr:`requires_human_review`).
    """

    market: Market
    vertical: Vertical
    total_budget: float
    lines: tuple[BudgetLine, ...] = ()

    @property
    def allocated(self) -> float:
        return round(sum(line.amount for line in self.lines), 2)

    @property
    def expected_conversions(self) -> float:
        return round(sum(line.expected_conversions for line in self.lines), 2)

    @property
    def expected_reach(self) -> int:
        return sum(line.expected_reach for line in self.lines)

    @property
    def blended_cost_per_conversion(self) -> float:
        conv = self.expected_conversions
        return round(self.allocated / conv, 2) if conv > 0 else float("inf")

    @property
    def requires_human_review(self) -> bool:
        """A budget allocation is consequential: a human always signs off before spend."""
        return True


# --------------------------------------------------------------------------- #
# 3. Reach and frequency
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ReachFrequency:
    """A deterministic reach / frequency / effective-reach estimate for the plan."""

    market: Market
    vertical: Vertical
    impressions: int
    unique_reach: int  # de-duplicated unique people reached (<= addressable)
    addressable: int  # consented, reachable audience ceiling
    average_frequency: float  # impressions / unique_reach
    effective_reach: int  # unique people at or above the effective-frequency threshold
    effective_frequency: int = 3  # the "3+" threshold, tunable
    rationale: str = ""
    citations: tuple[Citation, ...] = ()

    @property
    def reach_pct(self) -> float:
        """Unique reach as a fraction of the addressable audience (0..1)."""
        return round(self.unique_reach / self.addressable, 4) if self.addressable > 0 else 0.0


# --------------------------------------------------------------------------- #
# 4. Pacing / calendar (flight schedule)
# --------------------------------------------------------------------------- #
class PacingStrategy(StrEnum):
    """How spend is distributed across the flight (generic, tunable)."""

    EVEN = "even"  # equal spend per period
    FRONT_LOADED = "front_loaded"  # heavier at the start (launch push)
    BACK_LOADED = "back_loaded"  # heavier at the end (deadline / sale close)


@dataclass(frozen=True, slots=True)
class FlightLeg:
    """One period of the flight schedule with its paced budget and weight."""

    index: int
    start_date: str  # ISO date
    end_date: str  # ISO date
    weight: float  # 0..1 fraction of the total budget for this leg
    amount: float  # paced spend for this leg, market currency


@dataclass(frozen=True, slots=True)
class FlightSchedule:
    """The deterministic pacing calendar: legs that sum to the total budget."""

    market: Market
    vertical: Vertical
    start_date: str
    end_date: str
    strategy: PacingStrategy
    total_budget: float
    legs: tuple[FlightLeg, ...] = ()

    @property
    def paced_total(self) -> float:
        return round(sum(leg.amount for leg in self.legs), 2)


# --------------------------------------------------------------------------- #
# The aggregates (top-level artifacts) — always require human review
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class PlanRequest:
    """The inbound request for a campaign plan."""

    objective: str  # the campaign objective / topic, e.g. "savings account acquisition"
    market: Market
    vertical: Vertical
    total_budget: float
    start_date: date
    end_date: date
    flight_legs: int = 4
    pacing: PacingStrategy = PacingStrategy.EVEN
    max_segments: int = 5
    channels: tuple[Channel, ...] = ()  # empty => all benchmarked channels
    effective_frequency: int = 3


@dataclass(frozen=True, slots=True)
class Plan:
    """A single cited campaign plan bundling every artifact for an objective.

    The top-level consequential output of D2. It is spend-affecting, so it **always**
    requires human review (maker-checker): a maker (the agent) proposes and a checker (a
    qualified marketer / finance approver) disposes before any budget is committed.
    """

    id: str
    objective: str
    market: Market
    vertical: Vertical
    total_budget: float
    segments: tuple[SelectedSegment, ...]
    channel_mix: ChannelMix
    reach_frequency: ReachFrequency
    flight_schedule: FlightSchedule
    creative_brief: str = ""  # LLM-drafted, over the deterministic plan
    summary: str = ""  # LLM-narrated summary
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True
    generated_at: datetime = field(default_factory=utcnow)
