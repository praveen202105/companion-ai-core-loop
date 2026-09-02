import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as chat } from "./chat/route";
import { GET as memories } from "./memories/route";
import { POST as session } from "./session/route";

import { backendFetch } from "@/lib/server/backend";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

vi.mock("@/lib/server/backend", () => ({ backendFetch: vi.fn() }));
vi.mock("@/lib/server/principal", () => ({ getAuthenticatedPrincipal: vi.fn() }));

const principal = {
  provider: "google" as const,
  subject: "google-user-1",
  name: "Test User",
  email: "test@example.com",
  image: null,
};

describe("authenticated BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects an unauthenticated request before calling the backend", async () => {
    vi.mocked(getAuthenticatedPrincipal).mockResolvedValue(null);

    const response = await chat(
      new Request("http://localhost/api/chat", {
        method: "POST",
        body: JSON.stringify({ request_id: "request-001", message: "Hello" }),
      }),
    );

    expect(response.status).toBe(401);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("derives identity server-side and sends no session id", async () => {
    vi.mocked(getAuthenticatedPrincipal).mockResolvedValue(principal);
    vi.mocked(backendFetch).mockResolvedValue(
      new Response("event: message.delta\ndata: {\"delta\":\"Hi\"}\n\n", {
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    const response = await chat(
      new Request("http://localhost/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Subject": "forged" },
        body: JSON.stringify({ request_id: "request-001", message: "Hello" }),
      }),
    );

    expect(response.status).toBe(200);
    expect(backendFetch).toHaveBeenCalledWith(
      "/v1/me/chat",
      expect.objectContaining({
        body: JSON.stringify({ request_id: "request-001", message: "Hello" }),
      }),
      principal,
    );
    expect(vi.mocked(backendFetch).mock.calls[0]?.[1]?.body).not.toContain("session_id");
  });

  it("uses one user-scoped backend call for bootstrap and inspection", async () => {
    vi.mocked(getAuthenticatedPrincipal).mockResolvedValue(principal);
    vi.mocked(backendFetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ session: { id: "session-1" }, messages: [] })),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ memories: [], events: [], trace: null })),
      );

    const sessionResponse = await session();
    const memoriesResponse = await memories();

    expect(sessionResponse.status).toBe(200);
    expect(memoriesResponse.status).toBe(200);
    expect(backendFetch).toHaveBeenNthCalledWith(
      1,
      "/v1/me/session",
      { method: "POST" },
      principal,
    );
    expect(backendFetch).toHaveBeenNthCalledWith(
      2,
      "/v1/me/memories?status=active",
      {},
      principal,
    );
  });
});
