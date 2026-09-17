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

async function req(path: string, init?: RequestInit) {
  try {
    const r = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
    if (!r.ok) {
      const errText = await r.text();
      throw new Error(`${r.status} ${errText}`);
    }
    return r.json();
  } catch (err: any) {
    // Se falhar por erro de rede/CORS no browser, tenta proxy relativo do Next.js
    if (
      typeof window !== "undefined" &&
      (err.name === "TypeError" || String(err).includes("fetch") || String(err).includes("NetworkError"))
    ) {
      const r2 = await fetch(path, {
        ...init,
        headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
        cache: "no-store",
      });
      if (!r2.ok) {
        const errText2 = await r2.text();
        throw new Error(`${r2.status} ${errText2}`);
      }
      return r2.json();
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
    req(`/api/favorites/${jobId}${notes ? `?notes=${encodeURIComponent(notes)}` : ""}`, {
      method: "POST",
    }),
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

    try {
      const r = await fetch(`${API}/api/profile/resume`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) {
        const errText = await r.text();
        throw new Error(errText);
      }
      return r.json();
    } catch (err: any) {
      // Fallback para proxy interno relativo se o acesso direto à porta 8000 falhar
      if (
        typeof window !== "undefined" &&
        (err.name === "TypeError" || String(err).includes("fetch") || String(err).includes("NetworkError"))
      ) {
        const r2 = await fetch(`/api/profile/resume`, {
          method: "POST",
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
};
