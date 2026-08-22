// What a STRING can decide about the console's CSP, and nothing more.
//
// These tests are NOT sufficient, and saying so is the point. The defect this policy exists to
// remove was invisible to a header assertion: the header is byte-identical whether the document's
// script tags carry the nonce or not, because whether they do is decided by the RENDERING MODE,
// not by the policy string. A statically prerendered route emits bare script tags under a header
// that advertises a nonce, and `'strict-dynamic'` then disables the `'self'` fallback, so the
// half-fixed state blocks strictly more than the unfixed one did.
//
// Only `scripts/assert-hydratable.mjs` can see that, because only it starts the built server and
// reads the bytes. What follows covers the parts that really are string decisions: directive
// completeness, the three-state frame-ancestors read, the nonce shape, and the build-time refusal.

import assert from "node:assert/strict";
import test from "node:test";

import {
  ConfiguredEmptyError,
  UnhydratableCspError,
  WildcardOriginError,
  assertHydratableCsp,
  contentSecurityPolicy,
  frameAncestors,
  frameOptions,
  generateNonce,
} from "../lib/csp.mjs";

const REQUIRED = [
  "default-src",
  "base-uri",
  "form-action",
  "object-src",
  "script-src",
  "style-src",
  "img-src",
  "font-src",
  "connect-src",
  "frame-ancestors",
];

/** Split a policy string into a name -> value map, the way a browser parses it. */
function directives(csp) {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...value] = part.split(/\s+/);
        return [name.toLowerCase(), value.join(" ")];
      }),
  );
}

test("every required directive is present", () => {
  const parsed = directives(contentSecurityPolicy({}, "n0nce"));
  for (const name of REQUIRED) {
    assert.ok(parsed.has(name), `missing directive: ${name}`);
  }
});

test("no directive is ever empty, in any resolvable env state", () => {
  for (const env of [{}, { NEXT_PUBLIC_API_BASE: "" }, { NEXT_PUBLIC_FRAME_ANCESTORS: "a b" }]) {
    for (const nonce of [undefined, "n0nce"]) {
      for (const [name, value] of directives(contentSecurityPolicy(env, nonce))) {
        assert.notEqual(value, "", `directive ${name} is empty for env ${JSON.stringify(env)}`);
      }
    }
  }
});

test("script-src takes the nonce and strict-dynamic only when a nonce is minted", () => {
  assert.equal(
    directives(contentSecurityPolicy({}, "abc123")).get("script-src"),
    "'self' 'nonce-abc123' 'strict-dynamic'",
  );
  assert.equal(directives(contentSecurityPolicy({})).get("script-src"), "'self'");
});

test("object-src is 'none' and base-uri is 'self'", () => {
  const parsed = directives(contentSecurityPolicy({}, "n"));
  assert.equal(parsed.get("object-src"), "'none'");
  assert.equal(parsed.get("base-uri"), "'self'");
});

test("frame-ancestors resolves in three states, matching the FastAPI service", () => {
  assert.equal(frameAncestors({}), "'self'");
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }),
    "https://portal.client.example",
  );
  for (const blank of ["", "   ", "\t", "\n"]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: blank }),
      ConfiguredEmptyError,
      `blank value ${JSON.stringify(blank)} must be refused, not silently widened`,
    );
  }
});

test("X-Frame-Options is emitted only for the one policy it can express", () => {
  assert.equal(frameOptions("'self'"), "SAMEORIGIN");
  assert.equal(frameOptions("https://portal.client.example"), "");
});

test("connect-src widens to the API ORIGIN, never the full URL, and never for a proxy path", () => {
  assert.equal(
    directives(
      contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "https://api.client.example/v1/plans" }, "n"),
    ).get("connect-src"),
    "'self' https://api.client.example",
  );
  assert.equal(
    directives(contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "/planner/api" }, "n")).get(
      "connect-src",
    ),
    "'self'",
  );
  assert.throws(() => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "api.client.example" }, "n"));
});

test("nonces are unique and base64", () => {
  const seen = new Set();
  for (let i = 0; i < 50; i += 1) {
    const nonce = generateNonce();
    assert.match(nonce, /^[A-Za-z0-9+/]+={0,2}$/);
    seen.add(nonce);
  }
  assert.equal(seen.size, 50, "a reused nonce is a predictable nonce");
});

test("a layout without force-dynamic is refused at build time", () => {
  assert.throws(
    () => assertHydratableCsp("export default function RootLayout() { return null; }"),
    UnhydratableCspError,
  );
  assert.doesNotThrow(() => assertHydratableCsp('export const dynamic = "force-dynamic";'));
});

test("a wildcard frame-ancestors is refused in every spelling a config can render", () => {
  // The FastAPI half already refuses these. This is the OTHER emitter, and it is the one a
  // browser honours for the document, so closing only the service side left the console
  // framable by any origin while every check stayed green.
  for (const wildcard of ["*", "'*'", "null", "*.*"]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }),
      WildcardOriginError,
      `${JSON.stringify(wildcard)} must be refused, not passed through to the header`,
    );
  }
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example *" }),
    WildcardOriginError,
    "a wildcard standing beside named origins is still a wildcard",
  );
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "*,https://portal.client.example" }),
    WildcardOriginError,
    "a comma is not CSP list syntax, so a comma-joined wildcard must still be seen",
  );
  // A HOST-SOURCE wildcard is the spelling an exact-token set misses, and CSP honours it: every
  // subdomain may frame the console, including one an attacker takes over or registers on a
  // user-content domain. A real origin never contains an asterisk, so refusing the character
  // outright turns away nothing a deployment could correctly hold.
  for (const hostSource of [
    "https://*.client.example",
    "*.client.example",
    "https://*",
    "https://portal.client.example https://*.evil.example",
  ]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: hostSource }),
      WildcardOriginError,
      `${JSON.stringify(hostSource)} is a host-source wildcard and must be refused`,
    );
  }
});

test("the policy the proxy actually serves refuses a wildcard too", () => {
  // `contentSecurityPolicy` is what `proxy.ts` puts on the document response. Refusing inside
  // the resolver alone would be theatre if this path could still build a policy around it.
  for (const wildcard of ["*", "'*'", "null", "*.*"]) {
    assert.throws(
      () => contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }, "n0nce"),
      WildcardOriginError,
      `the served document policy must not carry frame-ancestors ${wildcard}`,
    );
  }
});

test("a legitimate named allowlist is unaffected by the wildcard refusal", () => {
  // A refusal that also refuses valid input is an outage, not a control.
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }),
    "https://portal.client.example",
  );
  assert.equal(
    frameAncestors({
      NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example https://intranet.client.example",
    }),
    "https://portal.client.example https://intranet.client.example",
  );
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'self'" }), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'none'" }), "'none'");
  assert.match(
    contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }, "n"),
    /frame-ancestors https:\/\/portal\.client\.example/,
  );
});

test("the unset and emptied states are exactly what they were before wildcards were refused", () => {
  // Pinned so a later edit cannot drift them. THIS repo refuses an emptied value rather than
  // mapping it to 'none', mirroring its own FastAPI half; the wildcard case is an addition to
  // that behaviour, never a replacement for it.
  assert.equal(frameAncestors({}), "'self'");
  for (const blank of ["", "   ", "\t", "\n", " \t\n "]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: blank }),
      ConfiguredEmptyError,
      `blank value ${JSON.stringify(blank)} must still be refused as configured-empty`,
    );
  }
});
