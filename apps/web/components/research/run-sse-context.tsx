"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactElement,
  type ReactNode,
} from "react";

const RECONNECT_DELAYS_MS: readonly number[] = [500, 2000];

export type RunSseEventHandler = (data: string) => void;

export interface RunSseSubscribe {
  (eventName: string, handler: RunSseEventHandler): () => void;
}

interface RunSseContextValue {
  subscribe: RunSseSubscribe;
}

const RunSseContext = createContext<RunSseContextValue | null>(null);

export interface RunSseProviderProps {
  runId: string;
  isTerminal: boolean;
  children: ReactNode;
}

function attachListener(
  source: EventSource,
  eventName: string,
  handlersRef: RunSseHandlersRef,
): void {
  source.addEventListener(eventName, (rawEvent) => {
    const messageEvent = rawEvent as MessageEvent<string>;
    const live = handlersRef.current.get(eventName);
    if (live === undefined) {
      return;
    }
    for (const handler of live) {
      handler(messageEvent.data);
    }
  });
}

type RunSseHandlersRef = {
  current: Map<string, Set<RunSseEventHandler>>;
};

export function RunSseProvider(props: RunSseProviderProps): ReactElement {
  const { runId, isTerminal, children } = props;
  const handlersRef = useRef<Map<string, Set<RunSseEventHandler>>>(new Map());
  const sourceRef = useRef<EventSource | null>(null);
  const attachedNamesRef = useRef<Set<string>>(new Set());

  const subscribe = useCallback<RunSseSubscribe>((eventName, handler) => {
    let set = handlersRef.current.get(eventName);
    if (set === undefined) {
      set = new Set();
      handlersRef.current.set(eventName, set);
    }
    set.add(handler);
    if (
      sourceRef.current !== null
      && !attachedNamesRef.current.has(eventName)
    ) {
      attachListener(sourceRef.current, eventName, handlersRef);
      attachedNamesRef.current.add(eventName);
    }
    return (): void => {
      const live = handlersRef.current.get(eventName);
      live?.delete(handler);
    };
  }, []);

  useEffect(() => {
    if (isTerminal) {
      return;
    }

    let isDisposed = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearReconnectTimer = (): void => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const closeActiveSource = (): void => {
      if (sourceRef.current !== null) {
        sourceRef.current.close();
        sourceRef.current = null;
        attachedNamesRef.current.clear();
      }
    };

    const open = (): void => {
      if (isDisposed) {
        return;
      }
      const source = new EventSource(`/api/research-runs/${runId}/events`);
      sourceRef.current = source;
      for (const eventName of handlersRef.current.keys()) {
        attachListener(source, eventName, handlersRef);
        attachedNamesRef.current.add(eventName);
      }

      source.onerror = (): void => {
        if (isDisposed) {
          return;
        }
        clearReconnectTimer();
        closeActiveSource();
        const nextDelay = RECONNECT_DELAYS_MS[attempt];
        attempt += 1;
        if (nextDelay === undefined) {
          isDisposed = true;
          return;
        }
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          open();
        }, nextDelay);
      };
    };

    open();

    return (): void => {
      isDisposed = true;
      clearReconnectTimer();
      closeActiveSource();
    };
  }, [runId, isTerminal]);

  const value = useMemo<RunSseContextValue>(() => ({ subscribe }), [subscribe]);

  return <RunSseContext.Provider value={value}>{children}</RunSseContext.Provider>;
}

export function useRunSseEvent(
  eventName: string,
  handler: RunSseEventHandler,
): void {
  const context = useContext(RunSseContext);
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (context === null) {
      return;
    }
    const stableHandler: RunSseEventHandler = (data) => {
      handlerRef.current(data);
    };
    return context.subscribe(eventName, stableHandler);
  }, [context, eventName]);
}
