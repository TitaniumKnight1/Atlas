import { useCallback, useEffect, useState, type DependencyList } from "react";

type AsyncState<TData> =
  | { state: "loading"; data?: undefined; error?: undefined }
  | { state: "ready"; data: TData; error?: undefined }
  | { state: "error"; data?: undefined; error: unknown };

export function useAsyncTask<TData>(loader: () => Promise<TData>, dependencies: DependencyList = []) {
  const [resource, setResource] = useState<AsyncState<TData>>({ state: "loading" });

  const reload = useCallback(async () => {
    setResource({ state: "loading" });
    try {
      setResource({ state: "ready", data: await loader() });
    } catch (error) {
      setResource({ state: "error", error });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { resource, reload };
}
