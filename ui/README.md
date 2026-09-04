# `campaign-planner` Campaign Planner - thin console

A small Next.js console over the `campaign-planner` FastAPI backend. It builds a cited campaign plan and
renders the audit-first view: selected audience, channel-mix budget allocation, reach /
frequency, the pacing calendar, and the maker-checker review banner.

```bash
npm ci
npm run build          # must compile (CI gate)
NEXT_PUBLIC_API_BASE=http://localhost:8101 npm run dev
```

## Source map

| Path | Owns |
|------|------|
| `lib/csp.mjs` | The ONE Content-Security-Policy module: the directive list, the three-state `frame-ancestors` read, the per-request nonce, and the build-time refusal. Nothing else builds a CSP. |
| `proxy.ts` | Mints the nonce per request and sets the policy on both the request headers (where Next reads the nonce) and the response headers (what the browser enforces). |
| `next.config.mjs` | The static headers a table CAN express, plus the two build refusals. Deliberately emits no CSP. |
| `app/layout.tsx` | `export const dynamic = "force-dynamic"`, required by the nonce policy. |
| `scripts/assert-hydratable.mjs` | Starts the BUILT server and asserts the served document's script tags carry the served nonce. |
| `tests/csp.test.mjs` | What a policy STRING can decide, and an explicit note on what it cannot. |

## Gate

```bash
make ui-check          # from the repo root: types, policy tests, build, hydration
```

Equivalently, from `ui/`: `npm run lint && npm test && npm run build && npm run assert-hydratable`.
`assert-hydratable` runs LAST and against the artefact the build just produced, because it is the
only check that executes the page. Everything cheaper has been fooled by the defect it catches:
the headers, the type-check, the build and the unit tests are all green on a console whose
controls silently do nothing.

The backend owns all business logic and citations; this UI is a thin presentation layer.
It never sends an `actor`: identity is resolved server-side (under the local profile a
"Demo identity" picker appears and sends the chosen persona as `X-Dev-Persona`).

Embedding knobs (see [../docs/embedding-and-identity.md](../docs/embedding-and-identity.md)):

- `NEXT_PUBLIC_BASE_PATH=/planner` mounts the console under a reverse-proxy sub-path.
- `NEXT_PUBLIC_EMBED=1` drops the console's own chrome (the host page owns it).
- `NEXT_PUBLIC_API_BASE` should point at the proxied API path when embedded same-origin.
