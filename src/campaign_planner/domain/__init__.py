"""Pure domain layer for the Campaign Planning system (D2).

Standard-library only: models (frozen dataclasses, the ``Citation`` provenance type, the
``Vertical`` and ``Market`` enums, and the ``Plan`` aggregate that always requires human
review), the deterministic engines, the exception hierarchy and JSON serialization. No
Google Cloud, ADK, FastAPI, or any framework is imported here, which is what lets the
managed stack be swapped for an on-prem one without touching domain logic.
"""
