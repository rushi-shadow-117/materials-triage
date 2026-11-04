// OIDC sign-in for the web app (authorization code with PKCE through oidc-client-ts), used
// when the build sets VITE_AUTH_MODE=oidc. The access token is stored where api.ts reads the
// bearer token, so every request carries it; the API reads the role from the token alone.
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { setToken } from "./api";

export const OIDC_ENABLED = import.meta.env.VITE_AUTH_MODE === "oidc";

let manager: UserManager | null = null;

export function userManager(): UserManager {
  if (!manager) {
    manager = new UserManager({
      authority: import.meta.env.VITE_OIDC_ISSUER ?? "http://localhost:8080/realms/materials-triage",
      client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "materials-triage-web",
      redirect_uri: `${window.location.origin}/callback`,
      post_logout_redirect_uri: `${window.location.origin}/`,
      response_type: "code",
      scope: "openid profile email",
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      automaticSilentRenew: true,
    });
    manager.events.addUserLoaded((user) => setToken(user.access_token));
    manager.events.addUserUnloaded(() => setToken(null));
  }
  return manager;
}

export async function signIn(): Promise<void> {
  await userManager().signinRedirect();
}

/** Handle the /callback URL after the identity provider redirects back. */
export async function finishSignIn(): Promise<void> {
  const user = await userManager().signinCallback();
  if (user) setToken(user.access_token);
}

export async function signOut(): Promise<void> {
  setToken(null);
  await userManager().signoutRedirect();
}
