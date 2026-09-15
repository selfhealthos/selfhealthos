import type { NextRequest } from "next/server";

import { handleProviderCallback } from "@/lib/oauth-callback";

// The path registered at dev.fitbit.com. It must keep resolving exactly here:
// Fitbit matches the redirect URL byte for byte, and changing this path means
// editing the app registration too. See lib/oauth-callback.ts for why the
// exchange is done server-side and how the origin is worked out.

export async function GET(request: NextRequest) {
  return handleProviderCallback(request, "fitbit", "Fitbit");
}
