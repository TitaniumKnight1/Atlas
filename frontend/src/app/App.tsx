import { EmptyState } from "../components/StateViews";
import { ProjectView } from "../features/project/ProjectView";
import "./App.css";
import { AppShell } from "./AppShell";
import { featureRoutes } from "./routes";
import { useHashRoute } from "./useHashRoute";

export function App() {
  const { routePath, navigate } = useHashRoute();
  const activeRoute = featureRoutes.find((route) => route.path === routePath) ?? featureRoutes[0];

  return (
    <AppShell activePath={routePath} onNavigate={navigate}>
      {activeRoute.id === "project" ? (
        <ProjectView />
      ) : (
        <EmptyState
          title={`${activeRoute.label} is planned`}
          detail={`${activeRoute.summary} This route is reserved so the next feature slice plugs into the same shell, API, and command UX patterns.`}
        />
      )}
    </AppShell>
  );
}
