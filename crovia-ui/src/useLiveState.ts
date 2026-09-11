/**
 * Polls the backend and hands the screens either live state or nothing.
 *
 * Polling rather than a socket: the backend already decides on a fixed beat, so
 * a stream would deliver the same value repeatedly, and a poll that fails is
 * far easier to fall back from than a socket that silently stops.
 */

import { useEffect, useRef, useState } from 'react';
import { LiveState, NearbyState, fetchLiveState, fetchMyWarnings, fetchNearby } from './api';

export type Connection = 'connecting' | 'live' | 'offline';

export function useLiveState(intervalMs = 5000) {
  const [state, setState] = useState<LiveState | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const ctl = new AbortController();

    const tick = async () => {
      const s = await fetchLiveState(ctl.signal);
      if (cancelled) return;
      if (s) {
        setState(s);
        setConnection('live');
      } else {
        setConnection('offline');
      }
    };

    tick();
    timer.current = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      ctl.abort();
      if (timer.current) clearInterval(timer.current);
    };
  }, [intervalMs]);

  return { state, connection };
}


/**
 * The citizen version of the same idea.
 *
 * A citizen account cannot read /api/state - that is operations data - so this
 * polls the endpoint that carries what the public may see. Using the operator
 * hook on the citizen screen left it reporting "offline" forever, whatever was
 * happening in the city.
 */
export function useNearby(intervalMs = 5000) {
  const [state, setState] = useState<NearbyState | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');

  useEffect(() => {
    let cancelled = false;
    const ctl = new AbortController();

    const tick = async () => {
      const s = await fetchNearby(ctl.signal);
      if (cancelled) return;
      if (s) {
        setState(s);
        setConnection('live');
      } else {
        setConnection('offline');
      }
    };

    tick();
    const timer = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      ctl.abort();
      clearInterval(timer);
    };
  }, [intervalMs]);

  return { state, connection };
}

/**
 * How many warnings this person has not read yet.
 *
 * The tab badge used to count a list of sample notifications written into the
 * app, so it read "3" for everybody, forever, including someone who had never
 * been warned about anything. A badge that is always on is a badge nobody
 * looks at.
 */
export function useUnreadWarnings(intervalMs = 15000) {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const w = await fetchMyWarnings();
      if (!cancelled) setUnread(w.filter((x) => !x.read).length);
    };
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return unread;
}
