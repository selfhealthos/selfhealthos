"use client";

// Browser-side calls go to the same origin Next.js serves - see
// next.config.ts's rewrites, which forward /api/* to Django over the internal
// network. Same origin means the session cookie rides along automatically.
// Unsafe methods need the CSRF token, which Django sets as a readable cookie
// (CSRF_COOKIE_HTTPONLY is False for exactly this reason).

const CSRF_COOKIE = "selfhealthos_csrftoken";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  // No cookie yet (fresh browser); this endpoint sets one.
  const res = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  const body = (await res.json()) as { csrf_token: string };
  return body.csrf_token;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Reads the RFC 9457 problem document the API returns on every failure. */
async function toError(res: Response): Promise<ApiError> {
  try {
    const problem = (await res.json()) as { title?: string; detail?: string };
    return new ApiError(res.status, problem.detail || problem.title || res.statusText);
  } catch {
    return new ApiError(res.status, res.statusText);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { credentials: "same-origin" });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

/**
 * Multipart upload. Separate from `apiSend` because the Content-Type header
 * must NOT be set by hand here: the browser generates it including the
 * multipart boundary, and overriding it with "multipart/form-data" produces a
 * body Django cannot parse and an empty request.FILES.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": await csrfToken() },
    body: form,
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

export async function apiSend<T>(
  path: string,
  { method = "POST", body }: { method?: string; body?: unknown } = {},
): Promise<T | null> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": await csrfToken(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return null;
  return (await res.json()) as T;
}
