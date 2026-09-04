# Embedding and identity: client integration guide (`campaign-planner` campaign-planner)

How to run the `campaign-planner` Campaign Planner standalone or embedded inside an existing client web
application, and how its server-verified identity works. Everything described here is
implemented in this repository; the "Further layers" section at the end points at the
reference repo for the designed extensions that are deliberately out of scope here.

The planner ships as two cooperating pieces:

- **Backend**: a FastAPI service (default port `8101`) exposing the plan endpoint
  (`POST /v1/plan`), health (`GET /healthz`), and the local persona list
  (`GET /v1/personas`).
- **UI**: a thin Next.js console (default port `3000`) that calls the backend and renders
  the cited plan. `NEXT_PUBLIC_EMBED=1` drops the console's own chrome
  (`ui/app/layout.tsx`, `ui/app/page.tsx`); the mount sub-path and API base are build-time
  env vars (`ui/next.config.mjs`, `ui/lib/api.ts`).

## 1. The three deployment shapes

| # | Shape | Use when the host... | Identity |
|---|-------|----------------------|----------|
| 1 | **Embedded, same-origin reverse proxy** | has an existing portal and controls its edge (nginx or Next.js rewrites). The planner is served under the parent origin (for example `portal.client.com/planner/`) and iframed first-party: no CORS, no third-party cookies. | Cloud IAP verifies the user at the edge; the proxy forwards `x-goog-iap-jwt-assertion`; the backend re-verifies it (`adapters/gcp/iap_identity.py`). |
| 2 | **Standalone behind Cloud IAP** | has no host app, or wants a separate console at its own URL (DNS + HTTPS LB + IAP). | Same IAP-verified assertion; IAP plus Workforce Identity Federation gives SSO against the client IdP. |
| 3 | **Local dev, no auth** | is evaluating offline: no IdP, no GCP, no network. | Seeded dev personas selected via the `X-Dev-Persona` header (`adapters/local/identity.py`). |

## 2. Run locally, no auth

```bash
make install            # python venv, [dev] extra only (no google-cloud-*)
make run-api            # FastAPI on :8101 (the Makefile sets MKT_CAMPAIGN_PROFILE=local)
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8101 npm run dev
# open http://localhost:3000
```

The local profile binds `LocalPersonaIdentityAdapter`: four seeded personas, no IdP, no
AD/LDAP. The UI shows a "Demo identity" picker only when `GET /healthz` reports
`profile: local`; it lists `GET /v1/personas` and sends the chosen id as `X-Dev-Persona`.
With no header the first persona is the default; an unknown id is a 401.

| id | subject | tenant | entitlement principals |
|----|---------|--------|-------------------------|
| `analyst` | `demo.analyst@bank.example` | `demo-bank` | `group:mkt-planner`, `group:marketing` |
| `approver` | `demo.approver@bank.example` | `demo-bank` | `group:mkt-planner`, `group:marketing`, `group:mkt-approver` |
| `auditor` | `demo.auditor@bank.example` | `demo-bank` | `group:audit` |
| `other-tenant` | `user@other-tenant.example` | `other-bank` | `group:mkt-planner` |

The `other-tenant` persona exists so per-tenant behaviour can be demoed offline. Curl
example (note: no `actor` anywhere in the body):

```bash
curl -s http://localhost:8101/v1/plan \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-Persona: approver' \
  -d '{"objective": "savings account acquisition", "market": "SG",
       "vertical": "banking", "total_budget": 120000,
       "start_date": "2026-07-01", "end_date": "2026-07-28"}'
```

The audit record for that plan carries `actor: demo.approver@bank.example`, resolved
server-side.

## 3. Secure deployment on GCP (Cloud IAP)

In the `gcp` (and `platform`) profile the identity port binds `IapIdentityAdapter`:
authentication is configured ON the GCP service, not hand-rolled in the app.

1. Deploy the API (Cloud Run) behind an HTTPS load balancer with **Identity-Aware Proxy**
   enabled. IAP authenticates every request against the configured IdP and injects a
   signed JWT in `x-goog-iap-jwt-assertion`.
2. Set `MKT_CAMPAIGN_IAP_AUDIENCE` to the IAP audience of the protected resource
   (`/projects/<NUM>/global/backendServices/<ID>` for an HTTPS LB). The adapter verifies
   signature, audience, issuer and expiry against Google's IAP keys; any failure is a 401.
   The assertion is never logged.
3. For a client workforce that lives in a non-Google IdP (Entra ID, Okta, AD FS),
   federate it into IAP with **Workforce Identity Federation**: users sign in against the
   client IdP and IAP still injects the verified assertion. No planner code changes.

The verified subject (email or sub claim) becomes the audit actor on every plan; the
`hd` claim maps to the tenant.

## 4. Embed inside an existing portal (same-origin reverse proxy)

Serve the planner under the parent origin at a sub-path, then iframe that path. Because
the frame is first-party there is no CORS to configure and no third-party-cookie issue.

### 4a. Proxy routes (nginx)

```nginx
# On https://portal.client.com
location /planner/ {
    proxy_pass         http://planner-ui.internal:3000/;   # the Next.js console
    proxy_set_header   Host $host;
}
location /planner/api/ {
    proxy_pass         http://planner-api.internal:8101/;  # the FastAPI backend
    proxy_set_header   Host $host;
    # Behind IAP the assertion header is forwarded automatically on the same origin.
}
```

Or, for a Next.js host app, the equivalent `rewrites()`:

```js
// next.config.mjs of the HOST portal
async rewrites() {
  return [
    { source: "/planner/api/:path*", destination: "http://planner-api.internal:8101/:path*" },
    { source: "/planner/:path*",     destination: "http://planner-ui.internal:3000/planner/:path*" },
  ];
}
```

### 4b. Build the console for the sub-path

```bash
# Build-time env for the planner UI
NEXT_PUBLIC_BASE_PATH=/planner        # mounts routes + assets under /planner
NEXT_PUBLIC_API_BASE=/planner/api     # API calls stay same-origin through the proxy
NEXT_PUBLIC_EMBED=1                   # host page owns the chrome
```

### 4c. The iframe tag (host page)

```html
<iframe src="/planner/" title="Campaign planner"
        style="width:100%;height:900px;border:0"></iframe>
```

### 4d. Allow the parent to frame the planner

The backend emits `Content-Security-Policy: frame-ancestors <allowlist>` on every
response. The default is `'self'` (plus `X-Frame-Options: SAMEORIGIN`); to allow specific
parent origins set a space-separated list, per the CSP grammar:

```bash
export MKT_CAMPAIGN_FRAME_ANCESTORS="https://portal.client.example https://admin.client.example"
```

`MKT_CAMPAIGN_FRAME_ANCESTORS` is read in three states, not two. Leaving it **unset** keeps
the restrictive `'self'` default. Setting it to a **blank** value is refused at boot: the
service will not start. That is deliberate, because a blank value renders
`Content-Security-Policy: frame-ancestors ` with an empty directive, which browsers discard
as a parse error, while the `X-Frame-Options` fallback is skipped at the same time, so the
clickjacking control disappears with no signal. If you meant "no parent may frame this",
that is the `'self'` default, so unset the variable. The same rule applies to the UI's
`NEXT_PUBLIC_FRAME_ANCESTORS`, which is refused at build time when set and blank.

### 4e. The console's own Content-Security-Policy

The document a browser frames is served by Next.js, not by FastAPI, so the console emits its
own policy. It cannot come from the static `headers()` table in `ui/next.config.mjs`, which
can express exactly one directive, `frame-ancestors`, as a constant: the console's policy needs
a per-request value, a script nonce.

The policy lives in one module, `ui/lib/csp.mjs`, and is enforced at two points that must not
both emit it:

1. **`ui/proxy.ts`** mints a fresh nonce per request and sets the built policy on BOTH the
   request headers (where Next reads the nonce it stamps onto every script tag it emits, under
   exactly the name `Content-Security-Policy`) and the response headers (what the browser
   enforces). Setting only one of the two fails silently in opposite directions.
2. **`ui/next.config.mjs`** emits the two static headers a table can express
   (`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`) and NO CSP at all. Two
   layers both emitting a CSP would hand the browser two policies to intersect, and the stricter
   one wins per directive.

`script-src` is `'self' 'nonce-<per-request>' 'strict-dynamic'`, and that is load-bearing rather
than cosmetic: Next ships its hydration bootstrap as an INLINE script carrying the Flight
payload, so a `script-src` without a nonce blocks it, `__next_f` never fills, React never
attaches, and the console is dead markup that looks correct in a screenshot. The policy also
carries `default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, and a
`connect-src` widened only to the ORIGIN of `NEXT_PUBLIC_API_BASE` (a same-origin proxy path
widens nothing).

Two things must both hold or the nonce makes things worse. The route must be DYNAMICALLY
rendered, because a statically prerendered page was built before the nonce existed and emits bare
script tags while the header advertises one, and `'strict-dynamic'` then switches off the
`'self'` fallback that had at least been loading the chunk scripts. That is why
`ui/app/layout.tsx` sets `export const dynamic = "force-dynamic"`, why `ui/next.config.mjs`
refuses to build without it, and why `ui/scripts/assert-hydratable.mjs` starts the BUILT server
and asserts every script tag in the served document carries the served nonce. A header assertion
cannot see this failure: the header is byte-identical in the working and the broken case.

When the UI is served cross-origin from the API during development, the CORS allowlist is
`MKT_CAMPAIGN_CORS_ORIGINS` (comma-separated, never `*`). When it is unset the localhost
dev origins apply only under a DELIBERATE `local` profile; a run that named no profile gets
an empty allowlist. Same-origin embedding needs no CORS at all.

## 5. The identity contract

- **Any client-supplied actor is ignored.** The API request schema has no `actor` field,
  and the backend would not read one. The audit actor is always the verified
  `Principal.actor` resolved by the active profile's `IdentityPort`
  (`api/security.py` builds a `RequestContext` from the request headers and maps
  `IdentityError` to HTTP 401).
- **The Principal carries entitlement principals and a tenant.** `campaign-planner`'s audience queries
  are market/vertical scoped and have no per-user ACL seam today, so `principals` is
  recorded for audit and reserved for future entitlement checks (the reference repo shows
  the pattern of merging them into governed-retrieval ACLs).
- **Profiles pick the verifier**: `local` = seeded personas (no auth, offline),
  `gcp`/`platform` = IAP assertion verification, `onprem` = fail-fast placeholder for the
  client's own IdP (OIDC/SAML). The contract test requires a `local` and an `onprem`
  binding for the identity port, like every other port.
- The CLI (`mkt-campaign`), demo scripts and eval harness call the domain service
  directly, in-process; the `actor` argument they pass is the audit subject for that
  trusted local entry point, not a network-asserted identity.

## 6. Configuration knobs

| Knob | Default | Meaning |
|------|---------|---------|
| `MKT_CAMPAIGN_PROFILE` | (unset = no choice) | Adapter profile: `local`, `gcp`, `platform`, `onprem`. Unset refuses the `local` relaxations rather than assuming them. |
| `MKT_CAMPAIGN_IAP_AUDIENCE` | (empty) | Expected IAP JWT audience; required in secure mode. |
| `MKT_CAMPAIGN_CORS_ORIGINS` | localhost dev origins under a deliberate `local`, otherwise empty | Comma-separated CORS allowlist; never `*`. |
| `MKT_CAMPAIGN_FRAME_ANCESTORS` | `'self'` when unset | Space-separated CSP `frame-ancestors` allowlist. Set and blank is refused at boot, never read as the default. |
| `MKT_CAMPAIGN_ALLOW_INSECURE_DEMO` | (unset = guard on) | The ONE opt-out from the loopback exposure bound. When the bound identity adapter does not verify the end user, a non-loopback peer gets 503; set this to exactly `1` to accept that exposure deliberately. `0`, `true`, blank and ` 1 ` all leave the guard on. |
| `NEXT_PUBLIC_FRAME_ANCESTORS` | `'self'` when unset | Space-separated CSP `frame-ancestors` allowlist for the CONSOLE document, resolved in the same three states as the API's. Set and blank is refused at `next build` / `next start`. |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8101` | API base the console calls (use the proxied path when embedded). Its ORIGIN is what widens the console CSP's `connect-src`. |
| `NEXT_PUBLIC_BASE_PATH` | (empty) | Sub-path the console mounts under (blank = standalone). |
| `NEXT_PUBLIC_EMBED` | (unset) | `1` drops the console chrome; host owns the page. |
| `X-Dev-Persona` (header) | first persona | Local profile only: selects a seeded persona. |

## 7. Client integration checklist

- [ ] Choose the shape: embedded same-origin proxy, standalone behind IAP, or local dev.
- [ ] Embedded: add the two proxy routes and the iframe tag on the host page.
- [ ] Embedded: build the UI with `NEXT_PUBLIC_BASE_PATH`, `NEXT_PUBLIC_API_BASE`
      (proxied path) and `NEXT_PUBLIC_EMBED=1`.
- [ ] Set `MKT_CAMPAIGN_FRAME_ANCESTORS` to the exact parent origins that may frame it.
- [ ] Secure mode: enable IAP on the service and set `MKT_CAMPAIGN_IAP_AUDIENCE`;
      federate the client IdP via Workforce Identity Federation if it is not Google.
- [ ] Do not send `actor` in any request body; it does not exist in the schema.
- [ ] Local demos: pick a persona in the UI or send `X-Dev-Persona`.

## 8. Security checklist

- [ ] `MKT_CAMPAIGN_PROFILE` set explicitly everywhere: `gcp` in production, `local` for an
      offline demo. There is no default, and an unset variable serves no identity.
- [ ] IAP enabled on the load balancer; direct ingress to the service blocked, so the
      assertion header cannot be spoofed around the proxy.
- [ ] `MKT_CAMPAIGN_IAP_AUDIENCE` matches the protected resource exactly.
- [ ] CORS allowlist is explicit per tenant (never `*`); same-origin embeds need none.
- [ ] `frame-ancestors` lists only the intended parent origins; default stays `'self'`. Never
      set the variable to a blank value to mean "default": the service refuses to boot on it.
- [ ] 401s on unknown/missing identity verified after deploy (`curl` without the
      assertion must fail).
- [ ] Audit records show the verified subject as `actor` for every plan.

## 9. Further layers (in the reference repo, not built here)

The reference implementation, `cdd-sow-research` (`docs/embedding-and-identity.md`
there), documents and partly implements the next layers, which this repo deliberately
leaves out of the current slice:

- **Mode 6 "launch in new tab"**: an OIDC Authorization Code + PKCE login flow
  (`/auth/*` routes) with a self-issued session cookie, for hosts that want a link-out
  instead of an iframe.
- **Cross-origin embedding (modes 4/5)**: a versioned loader / web component, a
  postMessage token handoff, and a bearer/JWKS-verifying identity adapter for hosts that
  cannot run a proxy or federate into IAP.
- **Per-hop hardening**: OAuth2 token exchange (on-behalf-of) plus Workload Identity and
  mTLS toward the shared platform services, DPoP / step-up auth for high-value actions.

All three land on seams that already exist here (`IdentityPort`, the settings-driven
adapter bindings, the env-driven embedding headers), so adopting them later is additive.
