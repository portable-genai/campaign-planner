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
  // `next dev` writes AGENTS.md and CLAUDE.md into this directory unless this is false; the
  // writer is node_modules/next/dist/server/lib/generate-agent-files.js. This repo's working
  // agreement is the AGENTS.md at its root and there is no tool-specific alias of it, so a
  // second one here is a second agreement to keep in step and CLAUDE.md is precisely the alias
  // the convention forbids. The generated prose also carries an em-dash, which the catalog's
  // house style forbids in shipped markdown. tests/unit/test_ui_agent_documents.py fails the
  // gate if this line goes away or if either file turns up on disk anyway.
  agentRules: false,
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
