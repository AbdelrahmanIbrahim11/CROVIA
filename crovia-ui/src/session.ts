/**
 * Who is signed in, and the token that proves it.
 *
 * The app used to "sign in" by choosing a role from a list. Nothing was
 * checked, no password was sent, and every screen was reachable by anyone who
 * opened the app. This talks to the real backend instead.
 *
 * Storage is deliberately simple. On web the token goes in localStorage, and
 * every read and write is wrapped, because a browser in private mode can throw
 * on access rather than returning nothing. If storage is unavailable the app
 * still works — the person is signed out when they reload, which is a small
 * inconvenience next to failing to start.
 *
 * When this ships as a phone build, swap the two functions at the bottom for
 * expo-secure-store. Nothing above them needs to change.
 */

import { API_BASE } from './api';

export type Role = 'normal' | 'admin' | 'authority';

export type Session = {
  token: string;
  role: Role;
  username: string;
  email: string;
  userId: string;
};

const KEY = 'crovia.session';

/** The signed-in session, if there is one. */
export function loadSession(): Session | null {
  const raw = readStore(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function saveSession(s: Session): void {
  writeStore(KEY, JSON.stringify(s));
}

export function clearSession(): void {
  writeStore(KEY, null);
}

/**
 * The header every protected call needs.
 *
 * Returns an empty object when signed out, so a caller can always spread it
 * without checking first.
 */
export function authHeader(): Record<string, string> {
  const s = loadSession();
  return s ? { Authorization: `Bearer ${s.token}` } : {};
}

type LoginResult =
  | { ok: true; session: Session }
  | { ok: false; error: string };

export async function signIn(
  email: string,
  password: string,
  userType: Role,
): Promise<LoginResult> {
  try {
    const r = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, user_type: userType }),
    });
    const body = await r.json();
    if (!r.ok) {
      return { ok: false, error: body?.detail ?? 'Could not sign in.' };
    }
    const session: Session = {
      token: body.access_token,
      role: body.role,
      username: body.username,
      email: body.email,
      userId: body.user_id,
    };
    saveSession(session);
    return { ok: true, session };
  } catch {
    return { ok: false, error: 'The CROVIA service is not reachable.' };
  }
}

export async function register(input: {
  username: string;
  password: string;
  email: string;
  number?: string;
  userType: Role;
}): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const r = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: input.username,
        password: input.password,
        email: input.email,
        number: input.number,
        user_type: input.userType,
      }),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      return { ok: false, error: body?.detail ?? 'Could not create the account.' };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: 'The CROVIA service is not reachable.' };
  }
}

/**
 * Sign out.
 *
 * The token is cleared locally first, and only then does the server get told.
 * If the network call fails the person is still signed out on this device,
 * which is the part that actually matters to them.
 */
export async function signOut(): Promise<void> {
  const header = authHeader();
  clearSession();
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', headers: header });
  } catch {
    // Already signed out locally. Nothing more to do.
  }
}

/** True when the token is still accepted by the server. */
export async function stillValid(): Promise<boolean> {
  const header = authHeader();
  if (!('Authorization' in header)) return false;
  try {
    const r = await fetch(`${API_BASE}/auth/me`, { headers: header });
    return r.ok;
  } catch {
    return false;
  }
}

// --- storage ---------------------------------------------------------------
// Swap these two for expo-secure-store when building for a phone.

function readStore(key: string): string | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function writeStore(key: string, value: string | null): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Private browsing, or site data blocked. The session lasts this run only.
  }
}
