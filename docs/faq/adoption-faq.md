# Adoption FAQ

For an engineering lead forking this repo as their institution's or brand's campaign-planning
base. The step-by-step is [`docs/ADOPTING.md`](../ADOPTING.md); this answers the "will it
hurt later?" questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`campaign_planner`), the CLI entry point
(`mkt-campaign`), the `MKT_CAMPAIGN_` env prefix, the resource-id stem and the distribution
name in one pass (preview with `--dry-run`, apply with `--yes`). Then recreate the venv,
`pip install -e ".[dev]"`, and run `make gate`. The script does the mechanical rename; the
human decisions (region, IdP, vertical / market seed data, eval golden set) are the checklist
in `ADOPTING.md`.

### If several brands fork this, how does each take upstream fixes?

Track upstream via **git tags** (semver). The repo declares a **core-vs-adopter-owned boundary** (ADOPTING §2): upstream owns
the domain engines, `ports/`, `tests/contract/`, the eval harness mechanics and CI; you own
`config/settings.yaml` values, the seeded audience / benchmark fixtures, `adapters/onprem/*`,
UI theming and the eval golden set. Rebase your adopter-owned changes onto each release rather
than merging `main` continuously, so conflicts stay in files you were told to expect.

### Is there a separate kernel module I keep untouched?

Not yet, and this is stated honestly. The vertical-neutral machinery (`Citation`,
`LlmRequest` / `LlmResponse`, `AuditEvent`, `EvalReport`, `Severity`, the guardrail types)
and the vertical artifacts (`Plan`, `ChannelMix`, `AudienceSegment`, `ReachFrequency`,
`FlightSchedule`) currently **live together in `domain/models.py`**, with the boundary
described in that module's docstring rather than split into a named `domain/kernel.py`. The
practices audit records this as the open A7 item. When you fork, treat the neutral types as
upstream-owned and the artifact models as yours; a later upstream release may extract the
kernel into its own module.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list, and the contract test enforces it: define the
`@runtime_checkable` Protocol under `ports/`, re-export it from `ports/__init__.py`, implement
one adapter per profile (at least `local` and `onprem`), bind all of them under `adapters:`
in `config/settings.yaml`, add the port to `PORT_PROTOCOLS` in
`tests/contract/test_port_parity.py`, add a `cached_property` on the `Container`, and wire it
in `api/deps.py`. See [`CONTRIBUTING.md`](../../CONTRIBUTING.md). (Note: the port-map guard
is currently one-directional, so a binding with no `PORT_PROTOCOLS` entry will not fail
loudly; add the entry.)

### How do I add a new sub-service or output panel?

A sub-service is pure domain: add `domain/<name>_service.py` (stdlib only, deterministic),
re-export it from `domain/services.py`, construct it in the `CampaignPlanService` orchestrator
(`domain/plan_service.py`) and in `api/deps.py`, and unit-test it. For an output panel, the
renderer (`scripts/render_plan_ui.py`) already renders the attached plan artifacts; add a
`data-panel` hook so the demo walkthrough can target it.

### How do I change the taxonomy (channel kinds, objective kinds)?

The ten vocabularies are `StrEnum`s (via the shared `hex-service-kit` commons) and the
engines are typed on `str`, so members ARE their wire values and you extend the vocabulary
without editing engine code. Serialized JSON values are the enum strings. To replace a
taxonomy wholesale for a different vertical, edit the enums in `domain/models.py` and the
label maps in the UI.

### Can I retune the optimiser numbers without touching code?

Partly today, and this is called out honestly. The engine tunables are already
**dataclass fields, not magic constants** (`BudgetAllocationService.saturation_frequency=3.0`
and `epsilon=0.01`; the `effective_frequency=3` "3+" threshold), and the eval thresholds live
in `eval/rubrics/*.yaml`. But there is **not yet** a `policy:` section in
`config/settings.yaml` with a `from_policy(...)` that threads these into the engines: the
orchestrator constructs `BudgetAllocationService()` with its defaults. Retuning today means
overriding the dataclass fields at construction; wiring a `policy:` settings block is the open
B4 item. If your compliance or finance function must own these numbers as configuration, plan
that small addition as part of adoption.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate (check F2, PASS). The renderer and the demo
server emit stable `data-*` evidence hooks for every load-bearing figure. `make demo-selftest`,
which `make gate` runs, builds all four live plans in process and then starts the REAL demo
server on an ephemeral port, walks every presenter step over HTTP, and compares each hook in the
served bytes against the value the running app just computed, so a refactor that breaks a step
or quietly stops recomputing a figure fails the gate rather than surfacing in front of an
audience. `make demo-browser` adds the last layer: headless Chromium loads the same served
pages and reads the figures out of the live DOM. Playwright is pinned in the `[demo]` extra
rather than `[dev]`, because the browser binary is a network download and the day-one offline
install must not need one; that stage skips itself when the extra is absent. Both stages have
been proven able to go RED against a planted stale figure and a stripped panel hook. If you
diverge, keep the hooks: they are the contract every stage reads.

### Does the CI run for my fork out of the box?

Yes. CI and the eval gate run on the `local` profile with **no cloud credentials and no org
secrets** (`.github/workflows/ci.yaml` sets `MKT_CAMPAIGN_PROFILE: local` and references no
`secrets.`), so a fork's build is green immediately. You add secrets only when you wire the
`gcp` / `platform` profiles. Note the eval gate measures the *reference* audience seed and
golden plans until you rebuild them for your own vertical / market; that is an explicit
adoption step, not a silent pass.
