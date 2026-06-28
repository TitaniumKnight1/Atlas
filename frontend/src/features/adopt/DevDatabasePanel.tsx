import { useCallback, useEffect, useState } from "react";

import {
  getDevDatabaseStatus,
  previewProvisionDevDatabase,
  dryRunProvisionDevDatabase,
  provisionDevDatabase,
  startDevDatabase,
  stopDevDatabase,
  previewTeardownDevDatabase,
  teardownDevDatabase,
  undoDevDatabaseCommand,
  type DevDatabaseStatus
} from "../../api/devDb";
import { runDependencyChecks, listDependencyChecks, type DependencyCheck } from "../../api/setup";
import { formatAuditRef } from "../../api/project";
import { Alert, Button, DefinitionGrid, DependencyChecksTable, SectionHeading, Surface } from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { ErrorState } from "../../components/StateViews";

interface DevDatabasePanelProps {
  projectId: string;
  serverDataPath: string;
  onAuditRef?: (auditRef: string | null) => void;
}

export function DevDatabasePanel({ projectId, serverDataPath, onAuditRef }: DevDatabasePanelProps) {
  const [status, setStatus] = useState<DevDatabaseStatus | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [dependencyChecks, setDependencyChecks] = useState<DependencyCheck[]>([]);
  const [dependencyBusy, setDependencyBusy] = useState(false);
  const [dependencyError, setDependencyError] = useState<unknown>(null);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<unknown>(null);

  const refreshStatus = useCallback(async () => {
    setStatusError(null);
    try {
      const response = await getDevDatabaseStatus(projectId);
      setStatus(response.data);
    } catch (error) {
      setStatusError(error);
      setStatus(null);
    }
  }, [projectId]);

  const refreshChecks = useCallback(async () => {
    try {
      const checks = await listDependencyChecks(projectId);
      setDependencyChecks(checks);
    } catch {
      setDependencyChecks([]);
    }
  }, [projectId]);

  useEffect(() => {
    void refreshStatus();
    void refreshChecks();
  }, [refreshStatus, refreshChecks]);

  async function handleRunPreflight() {
    if (!serverDataPath.trim()) {
      return;
    }
    setDependencyBusy(true);
    setDependencyError(null);
    try {
      await runDependencyChecks(projectId, { server_data_path: serverDataPath });
      await refreshChecks();
      await refreshStatus();
    } catch (error) {
      setDependencyError(error);
    } finally {
      setDependencyBusy(false);
    }
  }

  async function handleStart() {
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      const result = await startDevDatabase(projectId);
      onAuditRef?.(formatAuditRef(result.auditRef) ?? null);
      await refreshStatus();
    } catch (error) {
      setLifecycleError(error);
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function handleStop() {
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      const result = await stopDevDatabase(projectId);
      onAuditRef?.(formatAuditRef(result.auditRef) ?? null);
      await refreshStatus();
    } catch (error) {
      setLifecycleError(error);
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function handleTeardown() {
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      const result = await teardownDevDatabase(projectId);
      onAuditRef?.(formatAuditRef(result.auditRef) ?? null);
      await refreshStatus();
    } catch (error) {
      setLifecycleError(error);
    } finally {
      setLifecycleBusy(false);
    }
  }

  const canStart = status?.lifecycle === "stopped";
  const canStop = Boolean(status?.container_running);
  const hasContainer = status != null && status.lifecycle !== "absent";

  return (
    <Surface kind="card">
      <SectionHeading
        title="Dev database"
        detail="Provision a local MySQL Docker container matching the P2-2 connection string. Informational only — never blocks server start."
      />
      {statusError ? <ErrorState error={statusError} /> : null}
      {lifecycleError ? <ErrorState error={lifecycleError} /> : null}
      {status ? (
        <Surface kind="card">
          <DefinitionGrid
            items={[
              ["Lifecycle", status.lifecycle],
              ["Container running", status.container_running ? "yes" : "no"],
              ["MySQL reachable", status.mysql_reachable ? "yes" : "no"],
              ["Container", status.container_name ?? "—"],
              ["Volume", status.volume_name ?? "—"],
              ["Connection", status.connection_string]
            ]}
          />
          {status.message ? <p className="muted-copy">{status.message}</p> : null}
        </Surface>
      ) : null}
      <Alert severity="info" title="Preflight checks">
        Run M1 checks for Docker availability and port 3306 before provisioning.
      </Alert>
      {dependencyError ? <ErrorState error={dependencyError} /> : null}
      <div className="setup-step__actions">
        <Button loading={dependencyBusy} variant="secondary" disabled={!serverDataPath.trim()} onClick={() => void handleRunPreflight()}>
          Run dev DB preflight
        </Button>
      </div>
      <DependencyChecksTable checks={dependencyChecks} emptyDetail="Run preflight to record Docker and dev MySQL signals." />
      <CommandPanel
        title="Provision dev database"
        description="Creates atlas-dev-mysql with a named volume on 127.0.0.1:3306. Default undo removes the container but keeps the volume."
        executeLabel="Provision"
        onPreview={() => previewProvisionDevDatabase(projectId)}
        onDryRun={() => dryRunProvisionDevDatabase(projectId)}
        onExecute={() => provisionDevDatabase(projectId)}
        onUndo={(commandExecutionId) => undoDevDatabaseCommand(projectId, commandExecutionId)}
        onSuccess={() => {
          void refreshStatus();
        }}
        onUndoSuccess={() => {
          void refreshStatus();
        }}
      />
      <div className="setup-step__actions">
        <Button variant="secondary" disabled={!hasContainer || lifecycleBusy || !canStop} onClick={() => void handleStop()}>
          Stop container
        </Button>
        <Button variant="secondary" disabled={!canStart || lifecycleBusy} onClick={() => void handleStart()}>
          Start container
        </Button>
        <Button variant="secondary" disabled={!hasContainer || lifecycleBusy} onClick={() => void handleTeardown()}>
          Remove container + volume
        </Button>
      </div>
    </Surface>
  );
}
