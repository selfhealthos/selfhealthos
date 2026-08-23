import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Server components talk to Django directly over the internal Docker network.
// The browser's session cookie is forwarded so Django sees the same identity
// it would on a direct request.
const BASE = process.env.INTERNAL_API_URL ?? "http://django:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function serverGet<T>(path: string): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const res = await fetch(`${BASE}/api/v1${path}`, {
    headers: cookieHeader ? { cookie: cookieHeader } : {},
    cache: "no-store",
  });

  if (res.status === 401) redirect("/login");
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} on ${path}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

/** Same as serverGet but returns null on 404 instead of throwing. */
export async function serverGetOrNull<T>(path: string): Promise<T | null> {
  try {
    return await serverGet<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
