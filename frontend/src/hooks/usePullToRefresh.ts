import { useEffect, useRef, useState } from 'react';

interface Options {
  threshold?: number; // px to trigger refresh
  maxPull?: number; // visual cap
  onRefresh?: () => void | Promise<void>;
  enabled?: boolean;
}

/**
 * Pull-to-refresh for containers with internal scroll (overflow-y-auto).
 * Triggers when user pulls down from the top of the scroll container.
 */
export function usePullToRefresh<T extends HTMLElement>({
  threshold = 70,
  maxPull = 120,
  onRefresh,
  enabled = true,
}: Options = {}) {
  const ref = useRef<T | null>(null);
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const pulling = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;

    const isScrollableAtTop = () => {
      // Find the nearest scrollable ancestor inside `el` that is at top.
      // Default: check `el` itself.
      return (el.scrollTop ?? 0) <= 0;
    };

    const onTouchStart = (e: TouchEvent) => {
      if (refreshing) return;
      if (!isScrollableAtTop()) {
        startY.current = null;
        return;
      }
      startY.current = e.touches[0].clientY;
      pulling.current = false;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (startY.current == null || refreshing) return;
      const dy = e.touches[0].clientY - startY.current;
      if (dy <= 0) {
        setPull(0);
        return;
      }
      if (!isScrollableAtTop()) {
        setPull(0);
        return;
      }
      pulling.current = true;
      // Resistance curve
      const eased = Math.min(maxPull, dy * 0.5);
      setPull(eased);
      if (e.cancelable) e.preventDefault();
    };

    const onTouchEnd = async () => {
      if (!pulling.current) {
        setPull(0);
        startY.current = null;
        return;
      }
      const triggered = pull >= threshold;
      pulling.current = false;
      startY.current = null;
      if (triggered) {
        setRefreshing(true);
        setPull(threshold);
        try {
          if (onRefresh) await onRefresh();
          else window.location.reload();
        } finally {
          setRefreshing(false);
          setPull(0);
        }
      } else {
        setPull(0);
      }
    };

    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    el.addEventListener('touchcancel', onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [enabled, refreshing, pull, threshold, maxPull, onRefresh]);

  return { ref, pull, refreshing, threshold };
}
