"""Shared conversion from an escalated campaign Plan to an ``review-kit`` Review payload.

Lives in the adapter layer (not the pure domain) because it depends on the kit. Redacts the
subject descriptor, summary and citation snippets before they leave the process (P-04 boundary),
so no stray contact identifier reaches Hrz7 over the wire; Hrz7 redacts again before its own audit
write (defense in depth). The maker (the agent/analyst that originated the plan) and the tenant are
asserted here and trusted by Hrz7 because this is an authenticated S2S caller (per-hop OBO is the
deferred next layer).

Redaction note (deviation from the CDD / credit-memo templates): D2 is generic marketing over
fictional audience-benchmark data and ships no PII-redaction port or shared ``pii-kit`` (the
guardrail, not a redactor, is D2's content gate). So this module carries a small, self-contained
universal-identifier scrubber (email + separated phone runs) rather than importing a redaction
adapter that does not exist in this repo. It is defense-in-depth over already-fictional content,
never the primary control.
"""

from __future__ import annotations

import re

from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.models import Citation, Plan, Severity

# Cap the citations carried on the wire: enough to let a reviewer trace the plan without copying
# the entire evidence set into the review console.
_MAX_CITATIONS = 8

# The review console is a shared sink, so any stray contact identifier is masked regardless of the
# market that configured this producer. Emails are matched whole; phone-like runs require an
# internal separator so a plain budget integer (e.g. ``120000``) is never mistaken for a number.
_UNIVERSAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("PHONE", re.compile(r"\+?\d[\d().-]*(?:[ \t]\d[\d().-]*){1,}")),
)


def _redact(text: str) -> str:
    """Mask universal contact identifiers (email / phone) and collapse whitespace."""
    redacted = text
    for info_type, pattern in _UNIVERSAL_PATTERNS:
        redacted = pattern.sub(f"[{info_type}]", redacted)
    return re.sub(r"\s+", " ", redacted).strip()


def _severity(plan: Plan) -> Severity:
    """The plan's severity signal, or MEDIUM when it carries none.

    A campaign :class:`Plan` exposes no risk band or severity flag (unlike the CDD dossier's
    risk band): every plan is uniformly spend-affecting. So there is no signal to map and MEDIUM
    is the conservative default rule R8 routes on.
    """
    return Severity.MEDIUM


def _kit_citations(plan: Plan) -> tuple[KitCitation, ...]:
    seen: set[str] = set()
    out: list[KitCitation] = []
    for c in _plan_citations(plan):
        if c.source_id in seen:
            continue
        seen.add(c.source_id)
        out.append(KitCitation(source_id=c.source_id, title=c.title, snippet=_redact(c.snippet)))
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def _plan_citations(plan: Plan) -> list[Citation]:
    return list(plan.citations)


def plan_to_review(plan: Plan, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to Hrz7 when a campaign plan escalates."""
    descriptor = (
        f"Campaign plan for objective '{plan.objective}' in market {plan.market.value}, "
        f"vertical {plan.vertical.value}"
    )
    summary = (
        f"budget_committed={plan.total_budget:.0f}; segments={len(plan.segments)}; "
        f"channels={len(plan.channel_mix.lines)}; "
        f"expected_conversions={plan.channel_mix.expected_conversions:.0f}"
    )
    severity = _severity(plan)
    return Review(
        action="campaign_plan:build",
        subject=_redact(descriptor),
        maker=maker,
        tenant=tenant,
        summary=_redact(summary),
        severity=severity.value,
        # A budget commitment always warrants four-eyes (a maker proposes, a checker disposes).
        required_approvals=2,
        sod_group="campaign-maker-checker",
        case_ref=plan.id,
        citations=_kit_citations(plan),
    )
