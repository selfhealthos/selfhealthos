import { type NextRequest, NextResponse } from "next/server";

// Where Fitbit sends the browser back to.
//
// This is a Next route handler rather than a Django endpoint because the path
// registered at dev.fitbit.com sits under the frontend's URL space - next.config.ts's
// rewrites only cover /api, /admin, /static and /media, so this one is ours to
// handle. Landing on a page beats landing on a JSON document.
//
// **Fitbit never fetches this URL.** It returns a 302 and the browser follows
// it, which is why any hostname the operator's own browser can resolve works
// here, public or not - only the person authorising ever has to reach it.
//
// The browser arrives with its session and CSRF cookies for this origin, so
// the exchange below is made as the signed-in person - no token is passed
// through the URL and the code never reaches client-side JavaScript.

const SETTINGS = "/settings";
const CSRF_COOKIE = "selfhealthos_csrftoken";
const BASE = process.env.INTERNAL_API_URL ?? "http://django:8000";

/**
 * The origin the browser actually used.
 *
 * NOT `request.nextUrl.origin`. Docker sets `HOSTNAME` to the container id,
 * Next's standalone server takes its own hostname from that, and the origin
 * then comes out as `https://3f9a1c2b4d5e:3000` — a name that resolves nowhere
 * and a port that is not published. Redirecting there dead-ends the browser
 * on DNS_PROBE_FINISHED_NXDOMAIN, and sending it as an `Origin` header fails
 * Django's CSRF check for good measure.
 *
 * `host` (or `x-forwarded-host` if a reverse proxy sets it) is what the
 * browser actually sent, so the headers are authoritative for what the
 * person typed — which also keeps someone who reached the box by IP on that
 * IP, rather than bouncing them to a hostname their session cookie is not
 * scoped to.
 */
function publicOrigin(request: NextRequest): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") ?? "https";
  if (host) return `${proto}://${host}`;
  return process.env.NEXT_PUBLIC_SITE_URL ?? request.nextUrl.origin;
}

function back(request: NextRequest, params: Record<string, string>) {
  const url = new URL(SETTINGS, publicOrigin(request));
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return NextResponse.redirect(url);
}

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams;

  // Fitbit reports a refusal here rather than by failing the redirect, so a
  // person who pressed "Deny" arrives looking exactly like a success.
  const denied = query.get("error");
  if (denied) {
    return back(request, {
      error: query.get("error_description") || denied,
    });
  }

  const code = query.get("code");
  const state = query.get("state");
  if (!code || !state) {
    return back(request, { error: "Fitbit did not return an authorization code." });
  }

  const csrf = request.cookies.get(CSRF_COOKIE)?.value;
  const cookie = request.headers.get("cookie") ?? "";
  if (!csrf) {
    return back(request, { error: "Your session expired during sign-in. Try connecting again." });
  }

  const response = await fetch(`${BASE}/api/v1/health/connections/exchange`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrf,
      cookie,
      // Django checks this against CSRF_TRUSTED_ORIGINS on unsafe methods, and
      // a server-side fetch sends no Origin of its own. Must be the public
      // origin: the container's own is not in the trusted list.
      Origin: publicOrigin(request),
    },
    body: JSON.stringify({ code, state }),
    cache: "no-store",
  });

  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as {
      detail?: string;
      title?: string;
    };
    return back(request, {
      error: problem.detail || problem.title || `Fitbit connection failed (${response.status}).`,
    });
  }

  return back(request, { connected: "fitbit" });
}
