/**
 * Pure redirect decisions for the client-side route guards.
 *
 * Kept free of React so the enforcement logic can be unit-tested directly.
 * Each function returns the path to redirect to, or `null` to render the
 * requested route. Authentication is the only gate: WorkOS SSO is the single
 * sign-in path, so there is no intermediate state to pin the user to.
 */
export interface AuthRouteState {
  isAuthenticated: boolean;
}

/** Guards authenticated app routes (e.g. /home). */
export function protectedRedirect(state: AuthRouteState): string | null {
  return state.isAuthenticated ? null : '/login';
}

/** Guards public routes (e.g. /login): sends already-authenticated users onward. */
export function publicRedirect(state: AuthRouteState): string | null {
  return state.isAuthenticated ? '/home' : null;
}
