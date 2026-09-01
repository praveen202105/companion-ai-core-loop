import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("names the companion", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { name: "Mira remembers." })).toBeInTheDocument();
  });
});
