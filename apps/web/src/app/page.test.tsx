import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

describe("Home", () => {
  afterEach(() => vi.unstubAllGlobals());

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
});
