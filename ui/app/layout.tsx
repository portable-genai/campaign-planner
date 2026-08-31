import type { Metadata } from "next";
import { ProvenanceBanner } from "./ProvenanceBanner";
import "./globals.css";

// REQUIRED by the nonce CSP, not a performance preference. `proxy.ts` mints a per-request script
// nonce, and Next can only stamp it onto the script tags of a DYNAMICALLY rendered route. A
// statically prerendered page was built before the nonce existed, so every script tag would be
// bare while the header advertises a nonce, and `'strict-dynamic'` then disables the `'self'`
// fallback: the page would be blocked harder than with no policy at all. `next.config.mjs`
// refuses to build if this line goes missing, and ui/scripts/assert-hydratable.mjs proves the
// served document actually carries the nonce.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Campaign Planner",
  description:
    "Cited campaign plans (audience selection, channel-mix budget allocation, reach / frequency, pacing) generic across banking and online retail and the JP/AU/SG markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // EMBED mode: the host page owns the chrome, so render the planner bare (the page also
  // hides its own title block; see app/page.tsx).
  const embed = process.env.NEXT_PUBLIC_EMBED === "1";
  return (
    <html lang="en">
      <body className={embed ? undefined : "min-h-screen"}>
        <ProvenanceBanner />
        {children}
      </body>
    </html>
  );
}
