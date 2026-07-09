import { useEffect, useMemo, useState } from "react";

import { formatAuditRef, undoCommandExecution } from "../../api/project";
import {
  checkoutRef,
  cloneRepository,
  compareCommits,
  createBranch,
  createCommit,
  deleteBranch,
  discoverGitRepositories,
  dryRunCloneRepository,
  dryRunDeleteBranch,
  dryRunPullRepository,
  fetchRepository,
  getGitDiff,
  getGitStatus,
  listGitRefs,
  listGitRepositories,
  previewCloneRepository,
  previewDeleteBranch,
  previewPullRepository,
  pullRepository,
  type GitCommit,
  type GitRef,
  type GitRepository,
  type GitStatus
} from "../../api/git";
import {
  Alert,
  Button,
  DefinitionGrid,
  Field,
  Input,
  ProgressBar,
  ProjectPicker,
  SectionHeading,
  StatusPill,
  Surface,
  Tabs
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useActiveProjectSelection } from "../../components/useActiveProjects";
import { useProjectStream } from "../../components/useProjectStream";

type GitTab = "repos" | "branches" | "changes" | "clone";

export function GitView() {
  const { resource: projectsResource, projects, selectedProjectId, setSelectedProjectId, removeProject } = useActiveProjectSelection();
  const [repos, setRepos] = useState<GitRepository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [refs, setRefs] = useState<GitRef[]>([]);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [diffSummary, setDiffSummary] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<GitTab>("repos");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mutationTick, setMutationTick] = useState(0);
  const [cloneUrl, setCloneUrl] = useState("");
  const [clonePath, setClonePath] = useState("");
  const [newBranch, setNewBranch] = useState("");
  const [deleteBranchName, setDeleteBranchName] = useState("");
  const [commitMessage, setCommitMessage] = useState("");
  const [compareBase, setCompareBase] = useState("HEAD~1");
  const [compareHead, setCompareHead] = useState("HEAD");
  const [longOpActive, setLongOpActive] = useState(false);
  const [lastAuditRef, setLastAuditRef] = useState<string | null>(null);

  const selectedRepo = repos.find((repo) => repo.git_repository_id === selectedRepoId) ?? null;
  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, ["op-progress"]);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    const projectId = selectedProjectId;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const rows = await listGitRepositories(projectId);
        if (cancelled) {
          return;
        }
        setRepos(rows);
        if (!selectedRepoId && rows.length > 0) {
          setSelectedRepoId(rows[0].git_repository_id);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, mutationTick, selectedRepoId]);

  useEffect(() => {
    if (!selectedProjectId || !selectedRepoId) {
      setStatus(null);
      setRefs([]);
      return;
    }
    const projectId = selectedProjectId;
    const repoId = selectedRepoId;
    let cancelled = false;
    async function loadRepoDetails() {
      try {
        const [statusData, refData] = await Promise.all([getGitStatus(projectId, repoId), listGitRefs(projectId, repoId)]);
        if (!cancelled) {
          setStatus(statusData);
          setRefs(refData);
        }
      } catch {
        if (!cancelled) {
          setStatus(null);
          setRefs([]);
        }
      }
    }
    void loadRepoDetails();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, selectedRepoId, mutationTick]);

  const latestProgress = useMemo(() => {
    const events = streamEvents.filter((event) => event.topic === "op-progress" && event.event_type === "OperationProgress");
    return events.length > 0 ? events[events.length - 1] : undefined;
  }, [streamEvents]);

  const opProgress = latestProgress
    ? {
        bytesReceived: Number(latestProgress.payload.bytes_received ?? 0),
        totalBytes: Number(latestProgress.payload.total_bytes ?? 0),
        message: String(latestProgress.payload.message ?? "Git operation…")
      }
    : null;

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  async function handleDiscover() {
    if (!selectedProjectId) {
      return;
    }
    await discoverGitRepositories(selectedProjectId);
    bumpMutation();
  }

  async function handleCompare() {
    if (!selectedProjectId || !selectedRepoId) {
      return;
    }
    const [commitRows, diff] = await Promise.all([
      compareCommits(selectedProjectId, selectedRepoId, compareBase, compareHead),
      getGitDiff(selectedProjectId, selectedRepoId, compareBase, compareHead)
    ]);
    setCommits(commitRows);
    setDiffSummary(diff);
  }

  return (
    <div className="feature-page">
      <header className="feature-header atlas-panel">
        <SectionHeading
          detail="Clone, fetch, pull, branch, commit, and compare — remotes are redacted by the backend; Atlas never expects raw credentials in the UI."
          eyebrow="Git"
          title="Version project changes deliberately"
        />
      </header>

      <Surface className="project-layout" kind="panel" padded={false}>
        <ProjectPicker
          loading={projectsResource.state === "loading"}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onSelect={setSelectedProjectId}
          onRemove={removeProject}
        />

        <section className="project-main">
          {!selectedProjectId ? (
            <EmptyState detail="Select a project to manage git repositories." title="No project" />
          ) : (
            <>
              <Tabs
                activeId={activeTab}
                ariaLabel="Git views"
                tabs={[
                  { id: "repos", label: "Repositories" },
                  { id: "branches", label: "Branches" },
                  { id: "changes", label: "Status & diff" },
                  { id: "clone", label: "Clone" }
                ]}
                onChange={(id) => setActiveTab(id as GitTab)}
              />

              {loading ? <LoadingState title="Loading repositories" detail="Reading git metadata." /> : null}
              {error ? <ErrorState error={error} onRetry={() => bumpMutation()} /> : null}

              {activeTab === "repos" ? (
                <div className="workspace-grid">
                  <Surface kind="card">
                    <SectionHeading detail="Discovered and cloned repositories. Remote URLs are backend-redacted." title="Repositories" />
                    <div className="setup-step__actions">
                      <Button variant="secondary" onClick={() => void handleDiscover()}>
                        Discover repos
                      </Button>
                    </div>
                    {repos.length === 0 ? (
                      <EmptyState detail="Discover existing repos or clone a new one." title="No git repositories" />
                    ) : (
                      <div className="project-list">
                        {repos.map((repo) => (
                          <button
                            className={repo.git_repository_id === selectedRepoId ? "project-card project-card--active" : "project-card"}
                            key={repo.git_repository_id}
                            type="button"
                            onClick={() => setSelectedRepoId(repo.git_repository_id)}
                          >
                            <span>
                              <strong>{repo.local_path}</strong>
                              <small>{repo.remote_url ?? "no remote"}</small>
                            </span>
                            <StatusPill status="idle">{repo.repository_role}</StatusPill>
                          </button>
                        ))}
                      </div>
                    )}
                  </Surface>

                  {selectedRepo && selectedProjectId ? (
                    <Surface kind="card">
                      <SectionHeading title="Repository status" />
                      {status ? (
                        <DefinitionGrid
                          items={[
                            ["Branch", status.branch_name ?? "—"],
                            ["HEAD", status.head_commit_sha.slice(0, 8)],
                            ["Dirty", status.is_dirty ? "yes" : "no"],
                            ["Ahead / behind", `${status.ahead_count} / ${status.behind_count}`],
                            ["Summary", status.summary]
                          ]}
                        />
                      ) : (
                        <LoadingState title="Reading status" detail="Querying worktree." rows={2} />
                      )}
                      {(longOpActive || opProgress) && (
                        <ProgressBar
                          indeterminate={!opProgress?.totalBytes}
                          label={opProgress?.message ?? "Waiting for git op-progress…"}
                          max={opProgress?.totalBytes ?? 100}
                          value={opProgress?.bytesReceived ?? 0}
                        />
                      )}
                      {!streamConnected ? (
                        <Alert severity="warn" title="SSE disconnected">
                          Clone/fetch/pull progress streams on op-progress.
                        </Alert>
                      ) : null}
                      {lastAuditRef ? (
                        <Alert severity="info" title="Last audited operation">
                          {lastAuditRef}
                        </Alert>
                      ) : null}
                      <CommandPanel
                        description="Fetch downloads remote refs. Pull may warn on dirty worktrees."
                        executeLabel="Fetch"
                        title="Fetch repository"
                        onDryRun={async () => ({ data: { command_type: "FetchRepository", valid: true, simulation: {} }, warnings: [] })}
                        onExecute={async () => {
                          setLongOpActive(true);
                          try {
                            const result = await fetchRepository(selectedProjectId, selectedRepo.git_repository_id);
                            setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
                            return result;
                          } finally {
                            setLongOpActive(false);
                          }
                        }}
                        onPreview={async () => ({
                          data: {
                            command_type: "FetchRepository",
                            summary: "Fetch remote refs",
                            risk_level: "MEDIUM",
                            preview: { git_repository_id: selectedRepo.git_repository_id }
                          },
                          warnings: []
                        })}
                        onSuccess={() => bumpMutation()}
                      />
                      <CommandPanel
                        description="Pull merges remote changes. Backend warns when the worktree is dirty."
                        executeLabel="Pull"
                        title="Pull repository"
                        onDryRun={() => dryRunPullRepository(selectedProjectId, selectedRepo.git_repository_id)}
                        onExecute={async () => {
                          setLongOpActive(true);
                          try {
                            const result = await pullRepository(selectedProjectId, selectedRepo.git_repository_id);
                            setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
                            return result;
                          } finally {
                            setLongOpActive(false);
                          }
                        }}
                        onPreview={() => previewPullRepository(selectedProjectId, selectedRepo.git_repository_id)}
                        onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                        onSuccess={() => bumpMutation()}
                      />
                    </Surface>
                  ) : null}
                </div>
              ) : null}

              {activeTab === "branches" && selectedProjectId && selectedRepo ? (
                <Surface kind="card">
                  <SectionHeading detail="Create, switch, or delete branches. Delete preview warns about unmerged commits." title="Branches" />
                  <Field label="New branch name">
                    <Input value={newBranch} onChange={(event) => setNewBranch(event.target.value)} />
                  </Field>
                  <div className="setup-step__actions">
                    <Button
                      disabled={!newBranch.trim()}
                      variant="primary"
                      onClick={() =>
                        void createBranch(selectedProjectId, selectedRepo.git_repository_id, newBranch).then(() => bumpMutation())
                      }
                    >
                      Create branch
                    </Button>
                  </div>
                  <div className="atlas-table-wrap">
                    <table className="atlas-table">
                      <thead>
                        <tr>
                          <th>Ref</th>
                          <th>Type</th>
                          <th>Commit</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {refs.map((ref) => (
                          <tr key={ref.ref_name}>
                            <td>
                              {ref.ref_name}
                              {ref.is_current ? " (current)" : ""}
                            </td>
                            <td>{ref.ref_type}</td>
                            <td>{ref.commit_sha.slice(0, 8)}</td>
                            <td>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() =>
                                  void checkoutRef(selectedProjectId, selectedRepo.git_repository_id, ref.ref_name).then(() => bumpMutation())
                                }
                              >
                                Switch
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Field label="Delete branch">
                    <Input value={deleteBranchName} onChange={(event) => setDeleteBranchName(event.target.value)} />
                  </Field>
                  <CommandPanel
                    description="Branch delete may be irreversible if commits are unmerged."
                    disabled={!deleteBranchName.trim()}
                    executeLabel="Delete branch"
                    title="Delete branch"
                    onDryRun={() => dryRunDeleteBranch(selectedProjectId, selectedRepo.git_repository_id, deleteBranchName)}
                    onExecute={() => deleteBranch(selectedProjectId, selectedRepo.git_repository_id, deleteBranchName)}
                    onPreview={() => previewDeleteBranch(selectedProjectId, selectedRepo.git_repository_id, deleteBranchName)}
                    onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                    onSuccess={() => bumpMutation()}
                  />
                </Surface>
              ) : null}

              {activeTab === "changes" && selectedProjectId && selectedRepo ? (
                <div className="workspace-grid">
                  <Surface kind="card">
                    <SectionHeading title="Worktree changes" />
                    {status ? (
                      <div className="atlas-table-wrap">
                        <table className="atlas-table">
                          <thead>
                            <tr>
                              <th>Path</th>
                              <th>Status</th>
                              <th>+/-</th>
                            </tr>
                          </thead>
                          <tbody>
                            {status.file_changes.map((change) => (
                              <tr key={change.path}>
                                <td>{change.path}</td>
                                <td>{change.change_status}</td>
                                <td>
                                  +{change.insertions}/-{change.deletions}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <LoadingState title="Loading status" detail="Reading worktree." rows={2} />
                    )}
                    <Field label="Commit message">
                      <Input value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} />
                    </Field>
                    <Button
                      disabled={!commitMessage.trim()}
                      variant="primary"
                      onClick={() =>
                        void createCommit(selectedProjectId, selectedRepo.git_repository_id, commitMessage).then(() => bumpMutation())
                      }
                    >
                      Commit
                    </Button>
                  </Surface>

                  <Surface kind="card">
                    <SectionHeading title="Compare & diff" />
                    <div className="setup-form-grid">
                      <Field label="Base ref">
                        <Input value={compareBase} onChange={(event) => setCompareBase(event.target.value)} />
                      </Field>
                      <Field label="Head ref">
                        <Input value={compareHead} onChange={(event) => setCompareHead(event.target.value)} />
                      </Field>
                    </div>
                    <Button variant="secondary" onClick={() => void handleCompare()}>
                      Compare
                    </Button>
                    {commits.length > 0 ? (
                      <div className="atlas-table-wrap">
                        <table className="atlas-table">
                          <thead>
                            <tr>
                              <th>Commit</th>
                              <th>Author</th>
                              <th>Message</th>
                            </tr>
                          </thead>
                          <tbody>
                            {commits.map((commit) => (
                              <tr key={commit.commit_sha}>
                                <td>{commit.commit_sha.slice(0, 8)}</td>
                                <td>{commit.author_name}</td>
                                <td>{commit.message_summary}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                    {diffSummary ? <pre className="command-json">{JSON.stringify(diffSummary, null, 2)}</pre> : null}
                  </Surface>
                </div>
              ) : null}

              {activeTab === "clone" && selectedProjectId ? (
                <Surface kind="card">
                  <SectionHeading detail="Clone is reversible via undo. Remote URL is redacted in list views after clone." title="Clone repository" />
                  <div className="setup-form-grid">
                    <Field label="Remote URL">
                      <Input value={cloneUrl} onChange={(event) => setCloneUrl(event.target.value)} placeholder="https://…" />
                    </Field>
                    <Field label="Destination path">
                      <Input value={clonePath} onChange={(event) => setClonePath(event.target.value)} placeholder="C:\\servers\\repo" />
                    </Field>
                  </div>
                  {(longOpActive || opProgress) && (
                    <ProgressBar
                      indeterminate={!opProgress?.totalBytes}
                      label={opProgress?.message ?? "Clone in progress…"}
                      max={opProgress?.totalBytes ?? 100}
                      value={opProgress?.bytesReceived ?? 0}
                    />
                  )}
                  <CommandPanel
                    description="Preview clone target, validate, then clone. Progress streams over op-progress."
                    disabled={!cloneUrl.trim() || !clonePath.trim()}
                    executeLabel="Clone"
                    title="Clone repository"
                    onDryRun={() => dryRunCloneRepository(selectedProjectId, { remote_url: cloneUrl, destination_path: clonePath })}
                    onExecute={async () => {
                      setLongOpActive(true);
                      try {
                        return await cloneRepository(selectedProjectId, { remote_url: cloneUrl, destination_path: clonePath });
                      } finally {
                        setLongOpActive(false);
                      }
                    }}
                    onPreview={() => previewCloneRepository(selectedProjectId, { remote_url: cloneUrl, destination_path: clonePath })}
                    onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                    onSuccess={() => bumpMutation()}
                  />
                </Surface>
              ) : null}
            </>
          )}
        </section>
      </Surface>
    </div>
  );
}
