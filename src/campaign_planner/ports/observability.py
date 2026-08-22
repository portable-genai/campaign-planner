"""Observability ports — the A5 (audit/trace) and A4 (eval gate) concerns.

Primary GCP adapters: a **Cloud Logging locked WORM bucket** for immutable audit, **Cloud
Trace via OpenTelemetry** for the planning-loop traces, and the **Gen AI evaluation
service** plus the A4 promotion gate for model risk.

Two of the three ports here are NOT declared in this file. ``ObservabilityTracerPort`` and
``EvaluationGatePort`` were hand-copied into sixteen repositories, and by the time anyone
compared them they disagreed: one had dropped the eval-gate port entirely, two had dropped its
``gate`` method (the half that can refuse a promotion), one returned ``str`` from an audit
``record`` that returns ``None`` everywhere else. A Protocol copied into N repos is N Protocols,
and only one of them gets fixed when a defect is found. They are re-exported from the commons
instead, which is what ``tests/contract/test_port_parity.py`` asserts by object IDENTITY (``is``)
rather than ``isinstance``: a look-alike copy satisfies a runtime_checkable Protocol, and only
``is`` can tell the copy from the original.

``AuditSinkPort`` stays declared here on purpose. It is typed in this repo's own vocabulary
(:class:`~campaign_planner.domain.models.AuditEvent`), so it is not a shared shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_eval_kit import EvaluationGatePort
from hex_service_kit.observability import ObservabilityTracerPort, TokenUsage

from ..domain.models import AuditEvent

__all__ = [
    "AuditSinkPort",
    "EvaluationGatePort",
    "ObservabilityTracerPort",
    "TokenUsage",
]


@runtime_checkable
class AuditSinkPort(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Write an immutable audit record (WORM)."""
        ...
