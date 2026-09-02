import { describe, expect, it } from "vitest";

import { verifiedGoogleSubject } from "./lib/auth-profile";

describe("Google identity validation", () => {
  it("accepts only a verified Google subject", () => {
    expect(verifiedGoogleSubject({ sub: "google-123", email_verified: true })).toBe(
      "google-123",
    );
    expect(verifiedGoogleSubject({ sub: "google-123", email_verified: false })).toBeNull();
    expect(verifiedGoogleSubject({ email_verified: true })).toBeNull();
  });
});
