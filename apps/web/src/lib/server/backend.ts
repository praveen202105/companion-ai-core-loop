import "server-only";

function configuration() {
  const baseUrl = process.env.API_BASE_URL;
  const internalKey = process.env.INTERNAL_API_KEY;
  if (!baseUrl || !internalKey) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("API_BASE_URL and INTERNAL_API_KEY are required");
    }
  }
  return {
    baseUrl: (baseUrl || "http://localhost:8000").replace(/\/$/, ""),
    internalKey: internalKey || "local-internal-key-change-me",
  };
}

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { baseUrl, internalKey } = configuration();
  const headers = new Headers(init.headers);
  headers.set("X-Internal-API-Key", internalKey);
  if (init.body) headers.set("Content-Type", "application/json");
  return fetch(`${baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}
