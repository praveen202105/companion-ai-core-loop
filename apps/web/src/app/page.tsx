import { CompanionApp } from "@/components/companion-app";
import { SignInScreen } from "@/components/sign-in-screen";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

export default async function Home() {
  const principal = await getAuthenticatedPrincipal();
  if (!principal) return <SignInScreen />;
  return (
    <CompanionApp
      user={{ name: principal.name, email: principal.email, image: principal.image }}
    />
  );
}
