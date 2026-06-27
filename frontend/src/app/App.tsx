import { ConfigView } from "../features/config/ConfigView";
import { GitView } from "../features/git/GitView";
import { EmptyState } from "../components/StateViews";
import { ProjectView } from "../features/project/ProjectView";
import { ResourceView } from "../features/resources/ResourceView";
import { SetupView } from "../features/setup/SetupView";
import "./App.css";
import { AppShell } from "./AppShell";
import { featureRoutes } from "./routes";
import { useBackendStatus } from "./useBackendStatus";
import { useHashRoute } from "./useHashRoute";

export function App() {
  const { routePath, navigate } = useHashRoute();
  const backendStatus = useBackendStatus();
  const activeRoute = featureRoutes.find((route) => route.path === routePath) ?? featureRoutes[0];

  return (
    <AppShell activeLabel={activeRoute.label} activePath={routePath} backendStatus={backendStatus} onNavigate={navigate}>
      {activeRoute.id === "project" ? (
        <ProjectView />
      ) : activeRoute.id === "setup" ? (
        <SetupView />
      ) : activeRoute.id === "resources" ? (
        <ResourceView />
      ) : activeRoute.id === "git" ? (
        <GitView />
      ) : activeRoute.id === "config" ? (
        <ConfigView />
      ) : (
        <EmptyState
          title={`${activeRoute.label} is planned`}
          detail={`${activeRoute.summary} This route is reserved so the next feature slice plugs into the same shell, API, and command UX patterns.`}
        />
      )}
    </AppShell>
  );
}
