/** @type {import('next').NextConfig} */
// The Content-Security-Policy and X-Frame-Options are NOT set here. They carry a per-request
// script nonce, which a static `headers()` table cannot express, so `proxy.ts` owns them and
// builds them from `lib/csp.mjs`. Setting the policy in both places would hand the browser two
// policies to intersect, and the stricter one wins per directive, which would reinstate the
// frame-ancestors-only policy (no script-src, no object-src, no base-uri) this console shipped
// with, or the bare `script-src 'self'` that stops a Next console hydrating at all.
//
// What IS here are the two refusals. `next build` and `next start` both evaluate this file at
// module scope, so a layout that has lost its `force-dynamic` (and therefore cannot carry the
// nonce) fails the build instead of shipping a console whose controls silently do nothing, and an
// emptied NEXT_PUBLIC_FRAME_ANCESTORS fails it instead of serving an empty directive browsers
// discard.
import { readFileSync } from "node:fs";

import { assertHydratableCsp, frameAncestors } from "./lib/csp.mjs";

assertHydratableCsp(readFileSync(new URL("./app/layout.tsx", import.meta.url), "utf8"));
frameAncestors(process.env);

// NEXT_PUBLIC_BASE_PATH lets the console mount under a reverse-proxy sub-path (for example
// /planner) when embedded in a client portal; blank keeps standalone behaviour unchanged.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
