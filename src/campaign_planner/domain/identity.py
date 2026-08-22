"""Identity value objects for server-side, verified principals.

The planner never trusts a client-asserted ``actor`` or ACL. A :class:`Principal` is
resolved server-side by an :class:`~campaign_planner.ports.identity.IdentityPort` adapter
(local dev persona, GCP IAP-verified assertion, or an on-prem client IdP) from the inbound
transport context, and becomes the audit actor recorded with every spend-affecting plan.

Nothing is DECLARED here. These four names were hand-copied from the same source into every repo
in the catalog, so they are re-exported from :mod:`hex_service_kit.identity` instead: one
definition, one place to fix, and no drift for a contract test to discover later. The module
survives as the import path the domain and adapters already use, and the commons module is pure
standard library, so the domain core stays framework-free.
"""

from __future__ import annotations

from hex_service_kit.identity import (
    ANONYMOUS as ANONYMOUS,
)
from hex_service_kit.identity import (
    IdentityError as IdentityError,
)
from hex_service_kit.identity import (
    Principal as Principal,
)
from hex_service_kit.identity import (
    RequestContext as RequestContext,
)

__all__ = ["ANONYMOUS", "IdentityError", "Principal", "RequestContext"]
