import { useEffect, useMemo, useState } from "react";

import {
  adoptRepository,
  applyRepoNormalization,
  dryRunAdoptRepository,
  dryRunRepoNormalization,
  getPathway2Status,
  previewAdoptRepository,
  previewRepoNormalization,
  undoPathway2Command,
  type InlineSecretFinding,
  type Pathway2Status,
  type StructureScorecard
} from "../../api/pathway2";
import { listProjects, type ProjectSummary } from "../../api/project";
import {
  Badge,
  Button,
  CellStack,
  DefinitionGrid,
  Field,
  Input,
  InputGroup,
  SectionHeading,
  StatusPill,
  Surface
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";

type AdoptPhase = "input" | "adopted";

export function AdoptView() {
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [phase, setPhase] = useState<AdoptPhase>("input");
  const [rootPath, setRootPath] = useState("");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [status, setStatus] = useState<Pathway2Status | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];

  useEffect(() => {
    if (!projectId) {
      return;
    }
    let cancelled = false;
    const activeProjectId = projectId;
    async function loadStatus() {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const response = await getPathway2Status(activeProjectId);
        if (!cancelled) {
          setStatus(response.data);
        }
      } catch (error) {
        if (!cancelled) {
          setStatusError(error);
        }
      } finally {
        if (!cancelled) {
          setStatusLoading(false);
        }
      }
    }
    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const scorecard = status?.structure_scorecard;

  async function refreshStatus(activeProjectId: string) {
    const response = await getPathway2Status(activeProjectId);
    setStatus(response.data);
  }

  return (
    <div className="feature-stack">
      <SectionHeading
        title="Adopt team server"
        detail="Clone or import an existing FiveM repository and prepare the ADR-0027 overlay structure. P2-2 will set dev secrets; the server stays blocked until then."
      />

      {phase === "input" ? (
        <Surface>
          <InputGroup>
            <Field label="Local destination" hint="Clone target or existing server folder (project root).">
              <Input value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="C:\FXServer\team-server" />
            </Field>
            <Field label="Remote URL (optional)" hint="When set, Atlas clones into the destination before import.">
              <Input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} placeholder="https://github.com/org/fivem-server.git" />
            </Field>
          </InputGroup>
          <CommandPanel
            title="Adopt repository"
            description="Clone (optional), import as an Atlas project, and run config/resource discovery explicitly."
            executeLabel="Adopt repository"
            disabled={!rootPath.trim()}
            onPreview={() => previewAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onDryRun={() => dryRunAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onExecute={() => adoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onSuccess={(response) => {
              const adoptedId = String(response.data.project_id ?? "");
              if (adoptedId) {
                setProjectId(adoptedId);
                setPhase("adopted");
              }
            }}
          />
        </Surface>
      ) : null}

      {phase === "adopted" && projectId ? (
        <>
          <Surface>
            <div className="inline-actions">
              <StatusPill status="running">Pathway 2 adopt</StatusPill>
              {status?.pathway2_state.normalized ? <Badge variant="info">Normalized</Badge> : <Badge variant="neutral">Not normalized</Badge>}
              {status?.run_blocked_reason ? <Badge variant="neutral">Run blocked</Badge> : null}
            </div>
            {statusLoading ? <LoadingState title="Loading adopt status" detail="Refreshing structure scorecard and secret report." /> : null}
            {statusError ? <ErrorState error={statusError} /> : null}
            {scorecard ? <StructureScorecardView scorecard={scorecard} /> : null}
            {status?.inline_secrets?.length ? <InlineSecretsReport findings={status.inline_secrets} /> : null}
            {status?.run_blocked_reason ? (
              <EmptyState title="Server not ready to run" detail={status.run_blocked_reason} />
            ) : null}
          </Surface>

          <Surface>
            <SectionHeading
              title="Normalize base config"
              detail="Preview-first restructuring: placeholders in server.cfg, endpoints moved to gitignored server.cfg.local, exec trailer appended."
            />
            <CommandPanel
              title="Apply overlay structure"
              description="Mutates server.cfg through the command contract. Undo restores the original file byte-for-byte."
              executeLabel="Apply normalization"
              onPreview={() => previewRepoNormalization(projectId)}
              onDryRun={() => dryRunRepoNormalization(projectId)}
              onExecute={() => applyRepoNormalization(projectId)}
              onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
              onSuccess={() => void refreshStatus(projectId)}
              onUndoSuccess={() => void refreshStatus(projectId)}
            />
          </Surface>
        </>
      ) : null}

      {projects.length > 0 && phase === "input" ? (
        <Surface>
          <SectionHeading title="Resume adopted project" detail="Pick an existing workspace to continue normalization." />
          <div className="inline-actions">
            {projects.map((project) => (
              <Button
                key={project.project_id}
                variant="secondary"
                onClick={() => {
                  setProjectId(project.project_id);
                  setPhase("adopted");
                }}
              >
                {project.display_name}
              </Button>
            ))}
          </div>
        </Surface>
      ) : null}
    </div>
  );
}

function StructureScorecardView({ scorecard }: { scorecard: StructureScorecard }) {
  const rows = useMemo(
    () =>
      Object.entries(scorecard.checks).map(([key, value]) => ({
        key,
        label: key.replace(/_/g, " "),
        present: value.present
      })),
    [scorecard]
  );

  return (
    <div className="stack-gap-md">
      <DefinitionGrid
        items={[
          ["FiveM server", scorecard.looks_like_fivem_server ? "Yes" : "No"],
          ["Confidence", scorecard.confidence],
          ["Score", scorecard.score],
          ["server.cfg", scorecard.server_cfg_path ?? "Not found"],
          ["Git remote", scorecard.git_remote_redacted ?? "Not discovered"],
          ["Resources", scorecard.resource_count?.toString() ?? "—"]
        ]}
      />
      <div className="scorecard-grid">
        {rows.map((row) => (
          <CellStack key={row.key} title={row.label} detail={row.present ? "Present" : "Missing"} />
        ))}
      </div>
    </div>
  );
}

function InlineSecretsReport({ findings }: { findings: InlineSecretFinding[] }) {
  return (
    <div className="stack-gap-sm">
      <SectionHeading title="Inline secrets (masked)" detail="Production-shaped values detected in tracked config. Normalization will placeholderize these." />
      <ul className="plain-list">
        {findings.map((finding, index) => (
          <li key={`${finding.path}:${finding.line}:${index}`}>
            <code>
              {finding.path}:{finding.line}
            </code>{" "}
            — {finding.secret_type}: {finding.redacted_preview}
          </li>
        ))}
      </ul>
    </div>
  );
}
