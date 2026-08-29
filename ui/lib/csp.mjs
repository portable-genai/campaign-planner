// The console's Content-Security-Policy, in one module so it is built once and read twice.
//
// Emitting it inline in `next.config.mjs` through the static `headers()` table allows exactly
// one directive: `frame-ancestors`. That table cannot express a per-request
// value, which is what a script nonce is, so the console shipped with no `script-src` at all and
// therefore no restriction on where script could come from; and had one been added there, the
// only spelling the table can express is the bare `script-src 'self'` that BLOCKS Next's inline
// hydration bootstrap. Next serves that bootstrap as an INLINE script carrying the Flight
// payload: block it and `__next_f` never fills, React never attaches, and the console renders its
// controls as dead markup while the headers, the type-check, the build and every test stay green.
//
// So the policy lives here, the nonce is minted per request in `proxy.ts`, and `next.config.mjs`
// no longer emits a `Content-Security-Policy` at all. Two layers both setting it would hand the
// browser two policies to intersect, and the stricter one wins per directive, which is precisely
// how the original fleet defect resurfaces.
//
// `frameAncestors` here is the THREE-state read the FastAPI service already performs in
// `src/campaign_planner/api/app.py::_frame_ancestors`, and it is deliberately the same three
// states rather than the two-state `env.X || "'self'"` used elsewhere in the fleet: the two
// halves of one embedding posture must not disagree about what an emptied variable means.

/** Raised when an embedding variable is present but names nothing. Mirrors the service's refusal. */
export class ConfiguredEmptyError extends Error {}

/** Raised when an embedding variable names a wildcard instead of the origins it should allow. */
export class WildcardOriginError extends Error {}

/**
 * Exact tokens that must never be accepted as a framing ancestor.
 *
 * `'*'` is what a quoted Terraform variable or a YAML string renders. `*.*` is a host pattern
 * matching every name with a dot in it. `null` is the one that reads as harmless and is not: it
 * is not a wildcard by spelling and behaves as one, because a SANDBOXED iframe presents the
 * origin `null`, so a policy naming it hands framing rights to any page that can open one.
 */
const WILDCARD_TOKENS = new Set(["*", "'*'", "null", "*.*"]);

/**
 * True when an entry may not be a framing ancestor.
 *
 * Exact matching alone is not enough. `https://*.client.example` is in no token set, and CSP
 * honours a host-source wildcard: every subdomain may frame the console, including one an
 * attacker obtains by takeover or on a user-content subdomain. So ANY entry containing an
 * asterisk is refused, which turns away nothing a deployment could correctly hold, since a real
 * origin never contains the character.
 *
 * @param {string} entry
 * @returns {boolean}
 */
function isWildcard(entry) {
  return WILDCARD_TOKENS.has(entry) || entry.includes("*");
}

/**
 * Refuse an allowlist that names a wildcard, before the value can reach a response header.
 *
 * `src/campaign_planner/api/app.py::_refuse_wildcard` does this for the API surface, and it was
 * the only half that did. The document a browser frames is served by Next under the policy this
 * module builds, and `frame-ancestors` on the DOCUMENT is the header a browser actually consults
 * before framing it, so a deployment with the service half closed and this half open was still
 * framable by any origin.
 *
 * Tokens are split on commas as well as whitespace. CSP source lists are space separated, so a
 * comma form never names a valid origin anyway; splitting on it here means
 * `*,https://portal.example` is seen as the wildcard it contains rather than as one opaque token
 * that merely fails to equal `*`.
 *
 * @param {string} raw the configured value, before it is normalised
 * @param {string} envName the variable it came from, for the message
 * @throws {WildcardOriginError}
 */
function refuseWildcards(raw, envName) {
  for (const piece of String(raw).split(/[\s,]+/)) {
    const entry = piece.trim();
    if (entry && isWildcard(entry)) {
      throw new WildcardOriginError(
        `${envName} contains ${JSON.stringify(entry)}, which lets ANY origin frame this ` +
          "console: a wildcard frame-ancestors is the clickjacking control switched off, not " +
          `configured. Name the exact parent origins that may frame it, or unset ${envName} to ` +
          "keep the restrictive default.",
      );
    }
  }
}

/** Origin of the API base, when the console is deployed cross-origin from its service. */
function apiOrigin(env) {
  const raw = (env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!raw) return "";
  // A same-origin reverse-proxy path (for example `/planner/api`) is already covered by 'self'
  // and is not an origin, so it widens nothing.
  if (raw.startsWith("/")) return "";
  try {
    return new URL(raw).origin;
  } catch {
    throw new Error(
      `NEXT_PUBLIC_API_BASE must be an absolute URL or a same-origin path, got: ${raw}`,
    );
  }
}

/**
 * Who may frame this console, resolved in THREE states, never two.
 *
 * * unset: nobody expressed an intent, so the documented restrictive default `'self'` stands.
 * * set and blank: an intent WAS expressed and it names nothing. REFUSED rather than silently
 *   widened, because an empty `frame-ancestors` directive is a parse error browsers discard,
 *   which removes the clickjacking restriction in the one deployment shape that looks configured.
 *   `next.config.mjs` evaluates this at module scope, so the refusal is a build/boot refusal.
 * * set to a wildcard: also REFUSED, by {@link refuseWildcards}. A value that names everybody is
 *   not a narrower case of naming somebody.
 * * set with a value: used as given.
 *
 * @param {Record<string, string | undefined>} env
 * @returns {string}
 */
export function frameAncestors(env) {
  const raw = env.NEXT_PUBLIC_FRAME_ANCESTORS;
  if (raw === undefined || raw === null) return "'self'";
  const value = String(raw).trim();
  if (!value) {
    throw new ConfiguredEmptyError(
      "NEXT_PUBLIC_FRAME_ANCESTORS is set but empty. An empty CSP frame-ancestors directive is " +
        "discarded by browsers, leaving the console with no clickjacking protection. Unset it to " +
        "keep the 'self' default, or name the parent origins that may frame it.",
    );
  }
  refuseWildcards(value, "NEXT_PUBLIC_FRAME_ANCESTORS");
  return value.split(/\s+/).filter(Boolean).join(" ");
}

/**
 * The pre-CSP `X-Frame-Options` backstop, for the one policy it can express.
 *
 * A NAMED parent origin has no `X-Frame-Options` spelling, so it gets none rather than a value
 * that contradicts the CSP in an older agent. This mirrors the service middleware exactly, which
 * also emits the legacy header only for `'self'`.
 *
 * @param {string} ancestors resolved `frame-ancestors` value
 * @returns {string} the header value, or "" when none should be sent
 */
export function frameOptions(ancestors) {
  return ancestors === "'self'" ? "SAMEORIGIN" : "";
}

/**
 * The full default-deny policy.
 *
 * `style-src` carries `'unsafe-inline'` because the Next runtime injects critical CSS and there
 * is no nonce path for it. `script-src` does NOT: it takes the per-request nonce plus
 * `'strict-dynamic'`, so the nonced bootstrap may load its own chunks and nothing else may run.
 * Passing no nonce yields the strict `'self'` form, which is correct for any response that is not
 * a Next-rendered document and wrong for one that is.
 *
 * @param {Record<string, string | undefined>} env
 * @param {string} [nonce]
 * @returns {string}
 */
export function contentSecurityPolicy(env, nonce) {
  // The ONE dev-only relaxation, and the only place either token appears. Turbopack's HMR client
  // evaluates its module updates and opens a websocket back to the dev server, so `next dev`
  // served the production policy renders the page and never hydrates: React reports that eval is
  // unavailable, `__next_f` never fills and no control does anything. `next build` and
  // `next start` set NODE_ENV=production, so neither token can reach a deployment, and
  // `scripts/assert-hydratable.mjs` proves that against the BUILT artefact rather than by review.
  const isDev = env.NODE_ENV !== "production";
  const connectSrc = ["'self'", apiOrigin(env), isDev ? "ws: wss:" : ""]
    .filter(Boolean)
    .join(" ");
  const scriptSrc = [
    "script-src 'self'",
    nonce ? `'nonce-${nonce}' 'strict-dynamic'` : "",
    isDev ? "'unsafe-eval'" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    `frame-ancestors ${frameAncestors(env)}`,
  ].join("; ");
}

/** A fresh per-request nonce. Base64 of 16 random bytes from the Web Crypto global. */
export function generateNonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

/** Raised when the nonce policy and the rendering mode disagree, which serves un-hydratable HTML. */
export class UnhydratableCspError extends Error {}

/**
 * Refuse a build whose CSP mints a nonce the rendered HTML can never carry.
 *
 * Next can only stamp a per-request nonce onto the scripts of a DYNAMICALLY rendered route. A
 * statically prerendered page was built before the nonce existed, so it emits bare script tags
 * while the header advertises a nonce, and because `'strict-dynamic'` switches off the `'self'`
 * fallback, that combination blocks strictly MORE than the unfixed policy did. The failure is
 * invisible to every check that does not execute the page, so it is refused at build time.
 *
 * No I/O happens here: the caller passes the source as a string, which keeps this module
 * importable from the edge-runtime proxy.
 *
 * @param {string} layoutSource contents of `app/layout.tsx`
 * @throws {UnhydratableCspError}
 */
export function assertHydratableCsp(layoutSource) {
  if (!/export\s+const\s+dynamic\s*=\s*["']force-dynamic["']/.test(layoutSource)) {
    throw new UnhydratableCspError(
      'app/layout.tsx must set `export const dynamic = "force-dynamic"`. The CSP mints a ' +
        "per-request nonce, and Next can only stamp it onto script tags for a dynamically " +
        "rendered route. Statically prerendered HTML was built before the nonce existed, so " +
        "every script is blocked and the page never hydrates.",
    );
  }
}
