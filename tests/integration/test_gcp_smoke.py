"""Live GCP smoke tests (``-m integration``) — require real Google Cloud credentials.

Deselected by default (``pytest -m 'not integration'``). They exercise the managed-stack
adapters against live services; run only in an environment with ``[gcp]`` installed and ADC
configured. Kept thin so they document the live contract without being part of the offline
gate.
"""

from __future__ import annotations

import pytest

from campaign_planner.config import Settings, build_container
from campaign_planner.domain.models import Market, Vertical

pytestmark = pytest.mark.integration


def test_bigquery_audience_returns_segments_live():
    container = build_container(Settings.load("config/settings.yaml"))
    segments = container.audience.segments("savings", Market.SG, Vertical.BANKING)
    assert isinstance(segments, tuple)


def test_gemini_llm_generates_live():
    from campaign_planner.domain.models import LlmMessage, LlmRequest

    container = build_container(Settings.load("config/settings.yaml"))
    response = container.llm.generate(
        LlmRequest(messages=(LlmMessage(role="user", content="Say ok."),))
    )
    assert isinstance(response.text, str)
