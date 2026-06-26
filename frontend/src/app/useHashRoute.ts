import { useEffect, useState } from "react";

import { normalizeRoutePath } from "./routes";

export function useHashRoute() {
  const [routePath, setRoutePath] = useState(() => normalizeRoutePath(window.location.hash));

  useEffect(() => {
    function handleHashChange() {
      setRoutePath(normalizeRoutePath(window.location.hash));
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function navigate(path: string) {
    window.location.hash = path;
  }

  return { routePath, navigate };
}
