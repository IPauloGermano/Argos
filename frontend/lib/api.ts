const DEFAULT_TIMEOUT_MS = 12_000;

async function fetchWithRetry(
  url: string,
  init: RequestInit | undefined,
  headers: Record<string, string>,
  timeoutMs: number,
  retries = 1
): Promise<Response> {
  let lastErr: any = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const r = await fetch(url, { ...init, headers, cache: "no-store", signal: controller.signal });
      clearTimeout(timerId);
      // Retry controlado apenas em 502/503/504
      if ([502, 503, 504].includes(r.status) && attempt < retries) {
        await new Promise((res) => setTimeout(res, 500 * (attempt + 1)));
        continue;
      }
      return r;
    } catch (err: any) {
      clearTimeout(timerId);
      lastErr = err;
      if (err?.name === "AbortError") throw err;
      if (attempt < retries) {
        await new Promise((res) => setTimeout(res, 500 * (attempt + 1)));
        continue;
      }
      throw err;
    }
  }
  throw lastErr;
}

const getBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname || "localhost";
    const protocol = window.location.protocol || "http:";
    return `${protocol}//${host}:8000`;
  }
  return "http://127.0.0.1:8000";
};

const API = getBaseUrl();

/**
 * Returns the Authorization header value if NEXT_PUBLIC_API_TOKEN is set.
 * Admin-only endpoints require this token (Bearer <token>).
 * Read-only endpoints work without a token.
 */
function authHeaders(): Record<string, string> {
  const token =
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_TOKEN) ||
    (typeof window !== "undefined" &&
      (window as any).__NEXT_PUBLIC_API_TOKEN__);
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

async function req(path: string, init?: RequestInit, opts?: { timeoutMs?: number; retries?: number }) {
  const timeoutMs = opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const retries = opts?.retries ?? 1;
  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...((init?.headers as Record<string, string>) || {}),
  };

  try {
    const r = await fetchWithRetry(`${API}${path}`, init, baseHeaders, timeoutMs, retries);
    if (!r.ok) {
      const errText = await r.text();
      throw new Error(`${r.status} ${errText}`);
    }
    return r.json();
  } catch (err: any) {
    // AbortError = timeout
    if (err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms: ${path}`);
    }
    // Se falhar por erro de rede/CORS no browser, tenta proxy relativo do Next.js
    if (
      typeof window !== "undefined" &&
      (err.name === "TypeError" ||
        String(err).includes("fetch") ||
        String(err).includes("NetworkError"))
    ) {
      const controller2 = new AbortController();
      const timerId2 = setTimeout(() => controller2.abort(), DEFAULT_TIMEOUT_MS);
      try {
        const r2 = await fetch(path, {
          ...init,
          headers: baseHeaders,
          cache: "no-store",
          signal: controller2.signal,
        });
        clearTimeout(timerId2);
        if (!r2.ok) {
          const errText2 = await r2.text();
          throw new Error(`${r2.status} ${errText2}`);
        }
        return r2.json();
      } catch (err2: any) {
        clearTimeout(timerId2);
        throw err2;
      }
    }
    throw err;
  }
}

export const api = {
  get: (p: string) => req(p),
  put: (p: string, body: unknown) =>
    req(p, { method: "PUT", body: JSON.stringify(body) }),
  post: (p: string, body?: unknown) =>
    req(p, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: (p: string) => req(p, { method: "DELETE" }),
  getFavorites: () => req("/api/favorites"),
  addFavorite: (jobId: number, notes = "") =>
    req(
      `/api/favorites/${jobId}${notes ? `?notes=${encodeURIComponent(notes)}` : ""}`,
      { method: "POST" }
    ),
  removeFavorite: (jobId: number) =>
    req(`/api/favorites/${jobId}`, { method: "DELETE" }),
  sendFeedback: (jobId: number, isPositive: boolean) =>
    req(`/api/feedback/jobs/${jobId}`, {
      method: "POST",
      body: JSON.stringify({ is_positive: isPositive }),
    }),
  getFeedback: (jobId: number) => req(`/api/feedback/jobs/${jobId}`),
  uploadResume: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), 30_000); // uploads allow longer

    try {
      const r = await fetch(`${API}/api/profile/resume`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
        signal: controller.signal,
      });
      clearTimeout(timerId);
      if (!r.ok) {
        const errText = await r.text();
        throw new Error(errText);
      }
      return r.json();
    } catch (err: any) {
      clearTimeout(timerId);
      if (err.name === "AbortError") {
        throw new Error("Upload timed out after 30s");
      }
      // Fallback para proxy interno relativo se o acesso direto à porta 8000 falhar
      if (
        typeof window !== "undefined" &&
        (err.name === "TypeError" ||
          String(err).includes("fetch") ||
          String(err).includes("NetworkError"))
      ) {
        const r2 = await fetch(`/api/profile/resume`, {
          method: "POST",
          headers: authHeaders(),
          body: fd,
        });
        if (!r2.ok) {
          const errText2 = await r2.text();
          throw new Error(errText2);
        }
        return r2.json();
      }
      throw err;
    }
  },
  dismissJob: (jobId: number) =>
    req(`/api/jobs/${jobId}/dismiss`, { method: "POST" }),
  undismissJob: (jobId: number) =>
    req(`/api/jobs/${jobId}/undismiss`, { method: "POST" }),
};
