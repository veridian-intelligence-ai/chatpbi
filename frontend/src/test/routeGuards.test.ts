import { describe, it, expect } from 'vitest';
import { protectedRedirect, publicRedirect } from '@/lib/routeGuards';

describe('route guards', () => {
  it('sends unauthenticated users from protected routes to /login', () => {
    expect(protectedRedirect({ isAuthenticated: false })).toBe('/login');
  });

  it('lets unauthenticated users stay on public routes', () => {
    expect(publicRedirect({ isAuthenticated: false })).toBeNull();
  });

  it('renders protected routes for authenticated users', () => {
    expect(protectedRedirect({ isAuthenticated: true })).toBeNull();
  });

  it('sends authenticated users away from public routes to /home', () => {
    expect(publicRedirect({ isAuthenticated: true })).toBe('/home');
  });
});
