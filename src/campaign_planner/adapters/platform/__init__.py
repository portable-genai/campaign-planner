"""Remote-platform adapters — thin HTTP clients to the shared platform services.

When D2 runs inside the full Gemini Enterprise Agent Platform it reuses the shared platform
siblings (A1 guardrail gateway, A3 registry, A4 quality gate, A5 audit, and the shared data
plane) over HTTP instead of standalone GCP adapters. These clients construct cleanly with no
Google Cloud SDK; the request bodies are wired in the platform phase.
"""
