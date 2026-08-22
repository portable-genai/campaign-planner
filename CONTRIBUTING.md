# Contributing - Mkt2 Campaign Planner

## The bar

Every change keeps the **hard gate** green, in a fresh `python3.14` venv with the `[dev]`
extra only (no `google-cloud-*`):

```bash
make install        # python3.14 venv, [dev] only
make gate           # ruff check + ruff format --check + mypy + pytest + eval
cd ui && npm install && npm run build   # the Next.js console must compile
```

CI runs the same gate plus the UI build.

## Principles (from the reusable skills)

- **Deterministic domain services.** Any consequential decision (audience selection, budget
  allocation, reach / frequency, pacing) is pure, stdlib-only, replayable and unit-tested.
  The LLM only drafts the creative brief and narrates the summary; it never decides a number.
  No clock reads inside an engine - pass `as_of` / dates in as parameters.
- **Ports and adapters.** Add external capability behind a `typing.Protocol` (in `ports/`),
  with a `gcp` adapter (lazy SDK imports), a `local` adapter (SDK-free, deterministic,
  seedable) and an `onprem` fail-fast placeholder. The contract test proves parity.
- **Provenance + review.** Carry a `Citation` on every figure; set `requires_human_review`
  on every consequential aggregate.
- **Generic, multi-vertical, APAC.** No bank-only logic; banking and online retail are both
  configured verticals, and JP/AU/SG are config + seed. No hard-coded region/market branch.

## Conventions

- Markdown is em-dash-free; YAML scalars have no space-colon-space.
- Synthetic data is obviously fictional (FICTIONAL suffix, `example.test` URLs).
- Commits are authored solely by the user; no `Co-Authored-By` trailers.

## Adding an adapter

1. Implement the existing Protocol in `src/<package>/adapters/<profile>/<name>.py` with the
   single constructor `Adapter(settings)`; cloud SDK imports stay inside methods.
2. Add the dotted binding under the existing port in `config/settings.yaml` for that profile.
3. Add the adapter to the constructor and behavioral cases in
   `tests/contract/test_port_parity.py`; a placeholder must construct and fail fast.
4. Add profile-specific boundary tests, including unavailable service and malformed response
   cases. Do not copy business rules into the adapter.
5. Run `make gate`, the UI gate when applicable, and `make tf-validate` when deployment
   configuration changed.

## Adding a new port or sub-service

1. Add a `@runtime_checkable` Protocol in `src/<package>/ports/<name>.py` and re-export it once
   from `ports/__init__.py`.
2. Add one binding per declared profile in `config/settings.yaml`: working local, managed GCP
   or platform, and an honest on-premises implementation or fail-fast placeholder.
3. Register the Protocol in the `PORT_PROTOCOLS` map used by
   `tests/contract/test_port_parity.py`; the reverse set-equality assertion must stay green.
4. Wire the port only in the composition root or service factory. Domain services accept the
   Protocol dependency and never import an adapter.
5. Add behavioral parity tests and an end-to-end local test, then update the architecture,
   compliance evidence and adopter guidance.
