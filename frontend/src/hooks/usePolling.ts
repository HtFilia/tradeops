import { useCallback, useEffect, useRef } from "react";

type PollHandler = () => Promise<void> | void;

export function usePolling(handler: PollHandler, intervalMs: number): void {
  const handlerRef = useRef<PollHandler>(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (intervalMs <= 0) {
      return;
    }

    let active = true;
    let timer: number | null = null;

    const tick = async () => {
      if (!active) {
        return;
      }
      try {
        await handlerRef.current();
      } finally {
        if (active) {
          timer = window.setTimeout(tick, intervalMs);
        }
      }
    };

    timer = window.setTimeout(tick, intervalMs);

    return () => {
      active = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [intervalMs]);
}

export function useImmediate(handler: PollHandler): () => Promise<void> {
  return useCallback(async () => {
    await handler();
  }, [handler]);
}
