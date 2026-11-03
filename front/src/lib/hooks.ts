import { type DependencyList, useEffect, useState } from "react";

type AsyncState<T> = { data?: T; error?: string; loading: boolean };

/** Executa uma função assíncrona ao montar / quando as dependências mudam. */
export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [state, setState] = useState<AsyncState<T>>({ loading: true });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    fn()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: unknown) => alive && setState({ error: e instanceof Error ? e.message : String(e), loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
