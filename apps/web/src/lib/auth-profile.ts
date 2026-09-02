type GoogleIdentityProfile = {
  sub?: unknown;
  email_verified?: unknown;
};

export function verifiedGoogleSubject(profile: unknown): string | null {
  if (!profile || typeof profile !== "object") return null;
  const googleProfile = profile as GoogleIdentityProfile;
  if (googleProfile.email_verified !== true || typeof googleProfile.sub !== "string") {
    return null;
  }
  const subject = googleProfile.sub.trim();
  return subject.length > 0 && subject.length <= 255 ? subject : null;
}
