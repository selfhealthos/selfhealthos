import type { NextRequest } from "next/server";

import { handleProviderCallback } from "@/lib/oauth-callback";

// The path registered at developer.withings.com. Withings only accepts an
// **https** callback when you register it, which is the one real prerequisite
// this provider adds: on a LAN box with no public certificate that means
// compose.tls.yaml, or your own reverse proxy, before Withings can be
// connected at all. Withings never fetches this URL — the https is demanded at
// registration time, not at redirect time.

export async function GET(request: NextRequest) {
  return handleProviderCallback(request, "withings", "Withings");
}
