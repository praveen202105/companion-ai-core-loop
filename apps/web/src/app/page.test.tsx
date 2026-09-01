import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

describe("Home", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the protected companion experience", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ unlocked: false }), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<Home />);
    expect(
      await screen.findByRole("heading", { name: "Mira remembers what matters." }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Demo passcode")).toBeInTheDocument();
  });

  it("opens the inspectable memory drawer", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ unlocked: true })))
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
    render(<Home />);

    fireEvent.click(await screen.findByRole("button", { name: "Open memory inspector" }));

    expect(await screen.findByRole("dialog", { name: "Mira's memory inspector" })).toBeInTheDocument();
    expect(screen.getByText("The user's favorite drink is masala chai.")).toBeInTheDocument();
  });
});
