"""Platform ReviewRouterPort: submit the routed plan review to Hrz7 via ``review-kit``.

Builds the review from the escalated plan and submits it to the Hrz7 service intake
(``POST /v1/service/reviews``), S2S-authenticated. The Hrz7 base URL comes from the environment
(``HUMAN_REVIEW_URL``) and the S2S bearer/actor credentials reuse this repo's platform S2S env
convention (:mod:`campaign_planner.adapters.platform._s2s`: ``S2S_TOKEN`` /
``S2S_SIGNING_KEY``), so the review console is authenticated the same way as every other
sibling horizontal-platform service. No cloud SDK is involved (the kit uses stdlib ``urllib``
plus the wire-compatible S2S headers), so this module imports cleanly with no GCP SDK; it is
bound under the ``gcp`` and ``platform`` profiles because it makes a real network call to a
sibling service.
"""

from __future__ import annotations

from review_kit import ReviewClient

from ...config import Settings
from ...domain.models import Plan
from ...envread import read_env_setting
from .._review_payload import plan_to_review
from . import _s2s


class PlatformReviewRouter:
    """Submit escalated campaign plans to Hrz7 (rule R8), reusing the shared submission client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(  # pragma: no cover - needs live Hrz7
        self, plan: Plan, *, maker: str, tenant: str = ""
    ) -> None:
        base_url = read_env_setting("HUMAN_REVIEW_URL").value
        if not base_url:
            raise RuntimeError("HUMAN_REVIEW_URL must be set to route reviews to Hrz7")
        client = ReviewClient(
            base_url,
            token_env=_s2s.TOKEN_ENV,
            signing_key_env=_s2s.SIGNING_KEY_ENV,
        )
        client.submit(
            plan_to_review(plan, maker=maker, tenant=tenant), actor="mkt2-campaign-planner"
        )
