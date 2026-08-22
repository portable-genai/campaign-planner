"""Campaign Planning and Budget Allocation (D2) — a ports-and-adapters reference build.

Generic across banking and online retail and the JP/AU/SG markets, on the Gemini Enterprise
Agent Platform. The pure domain core (models + the deterministic audience-selection,
budget-allocation, reach/frequency and pacing engines) is framework-free; everything
external is reached through a typed port with swappable adapter profiles (gcp / local /
onprem). The LLM only drafts the creative brief and narrates the plan summary.
"""

__version__ = "0.0.1"
