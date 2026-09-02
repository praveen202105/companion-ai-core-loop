import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompanionApp } from "@/components/companion-app";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

import Home from "./page";

vi.mock("@/lib/server/principal", () => ({
  getAuthenticatedPrincipal: vi.fn(),
}));

vi.mock("@/app/actions", () => ({
  signInWithGoogle: vi.fn(),
  signOutOfMira: vi.fn(),
}));

const user = { name: "Praveen", email: "praveen@example.com", image: null };

describe("Home", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows Google sign-in when there is no authenticated user", async () => {
    vi.mocked(getAuthenticatedPrincipal).mockResolvedValue(null);

    render(await Home());

    expect(screen.getByRole("heading", { name: "Mira remembers what matters." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
  });

  it("opens the inspectable memory drawer", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ ready: true, messages: [] })))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              memories: [
                {
                  id: "memory-1",
                  canonical_key: "user:user:favorite_drink",
                  memory_type: "preference",
                  normalized_text: "The user's favorite drink is masala chai.",
                  value: "masala chai",
                  status: "active",
                  confidence: 0.98,
                  importance: 0.8,
                },
              ],
              events: [],
              trace: null,
            }),
          ),
        ),
    );
    render(<CompanionApp user={user} />);

    fireEvent.click(await screen.findByRole("button", { name: "Open memory inspector" }));

    expect(await screen.findByRole("dialog", { name: "Mira's memory inspector" })).toBeInTheDocument();
    expect(screen.getByText("The user's favorite drink is masala chai.")).toBeInTheDocument();
  });

  it("renders streamed deltas and applies the guarded final response", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: message.delta\ndata: {"delta":"Draft text"}\n\n'),
        );
        controller.enqueue(
          encoder.encode(
            'event: message.completed\ndata: {"id":"message-1","content":"Final text"}\n\n',
          ),
        );
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ ready: true, messages: [] })))
        .mockResolvedValueOnce(new Response(stream)),
    );
    render(<CompanionApp user={user} />);

    const composer = await screen.findByLabelText("Message Mira");
    fireEvent.change(composer, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("Final text")).toBeInTheDocument();
    expect(screen.queryByText("Draft text")).not.toBeInTheDocument();
  });

  it("shows the authenticated account in the chat header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ ready: true, messages: [] }))),
    );

    render(<CompanionApp user={user} />);

    expect(await screen.findByText("praveen@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
