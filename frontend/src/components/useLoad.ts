import { useCallback, useEffect, useState } from "react";

export type Load<T> =
  { status: "loading" } | { status: "error"; error: unknown } | { status: "ready"; data: T };

/** Load data on mount (and when `deps` change). `reload` fetches again; `set` replaces it. */
export function useLoad<T>(loader: () => Promise<T>, deps: readonly unknown[]) {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    loader()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: "error", error });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps are supplied by the caller
  }, [...deps, version]);

  const reload = useCallback(() => {
    setVersion((v) => v + 1);
  }, []);
  const set = useCallback((data: T) => {
    setState({ status: "ready", data });
  }, []);
  return { state, reload, set };
}
