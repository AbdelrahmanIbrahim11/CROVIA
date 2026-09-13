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

    // Old danger must not keep being drawn as if it were current.
    //
    // A failed poll used to leave the last good reading on screen for ever, so
    // a red critical zone stayed on the map long after the crowd had gone and
    // long after the connection had dropped - beside a header that correctly
    // said "backend offline". Anybody looking would have sent people to a
    // place that was empty.
    //
    // A single blip is tolerated, because one dropped request on a phone is
    // normal and clearing the map on every hiccup would be its own kind of
    // lying. After three in a row - about fifteen seconds - the map is emptied
    // and the screen says it has lost contact rather than showing a city it
    // can no longer see.
    let misses = 0;

    const tick = async () => {
      const s = await fetchLiveState(ctl.signal);
      if (cancelled) return;
      if (s) {
        misses = 0;
        setState(s);
        setConnection('live');
      } else {
        misses += 1;
        setConnection('offline');
        if (misses >= 3) setState(null);
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

    // Same reasoning as useLiveState above: a stale warning shown as live is
    // worse than an honest "no data".
    let misses = 0;

    const tick = async () => {
      const s = await fetchNearby(ctl.signal);
      if (cancelled) return;
      if (s) {
        misses = 0;
        setState(s);
        setConnection('live');
      } else {
        misses += 1;
        setConnection('offline');
        if (misses >= 3) setState(null);
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
/**
 * Anyone who wants to know when this person's messages change.
 *
 * The badge used to poll on its own fifteen-second timer, so after clearing the
 * list the screen said "Nothing to report" while the tab still showed 9+ for up
 * to a quarter of a minute. A number that disagrees with the list beside it is
 * worse than no number at all.
 */
const warningListeners = new Set<() => void>();

/** Call after deleting or clearing, so every badge updates at once. */
export function warningsChanged(): void {
  warningListeners.forEach((fn) => fn());
}

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
    // Re-count the moment something is deleted, rather than on the next tick.
    warningListeners.add(tick);
    return () => {
      cancelled = true;
      clearInterval(timer);
      warningListeners.delete(tick);
    };
  }, [intervalMs]);

  return unread;
}
