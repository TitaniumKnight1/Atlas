import { useEffect, useState } from "react";

import { listProjects, undoCommandExecution, type ProjectSummary } from "../../api/project";
import {
  applyConfigChange,
  dryRunConfigChange,
  formatMaskedSecret,
  getConfigFile,
  listConfigFiles,
  listSecretFindings,
  listValidationFindings,
  previewConfigChange,
  runSecretScan,
  runValidation,
  type ConfigFileSummary,
  type SecretFinding,
  type ValidationFinding
} from "../../api/config";
import { Alert, Button, CodeEditor, ProjectPicker, SectionHeading, Surface, Tabs } from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";

type ConfigTab = "editor" | "findings" | "secrets";

export function ConfigView() {
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [files, setFiles] = useState<ConfigFileSummary[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [loadedPath, setLoadedPath] = useState("");
  const [validationFindings, setValidationFindings] = useState<ValidationFinding[]>([]);
  const [secretFindings, setSecretFindings] = useState<SecretFinding[]>([]);
  const [previewDiff, setPreviewDiff] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ConfigTab>("editor");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mutationTick, setMutationTick] = useState(0);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];
  const selectedFile = files.find((file) => file.config_file_id === selectedFileId) ?? null;

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadFiles() {
      setLoading(true);
      setError(null);
      try {
        const rows = await listConfigFiles(projectId);
        if (!cancelled) {
          setFiles(rows);
          if (!selectedFileId && rows.length > 0) {
            setSelectedFileId(rows[0].config_file_id);
          }
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
    void loadFiles();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, mutationTick, selectedFileId]);

  useEffect(() => {
    if (!selectedProjectId || !selectedFileId) {
      setEditorContent("");
      setLoadedPath("");
      return;
    }
    const projectId = selectedProjectId;
    const fileId = selectedFileId;
    let cancelled = false;
    async function loadFile() {
      try {
        const view = await getConfigFile(projectId, fileId);
        if (!cancelled) {
          setEditorContent(view.content ?? "");
          setLoadedPath(view.path);
        }
      } catch {
        if (!cancelled) {
          setEditorContent("");
        }
      }
    }
    void loadFile();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, selectedFileId]);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    void listValidationFindings(selectedProjectId).then(setValidationFindings).catch(() => setValidationFindings([]));
    void listSecretFindings(selectedProjectId).then(setSecretFindings).catch(() => setSecretFindings([]));
  }, [selectedProjectId, mutationTick]);

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  async function handleRunValidation() {
    if (!selectedProjectId) {
      return;
    }
    await runValidation(selectedProjectId, selectedFileId);
    const findings = await listValidationFindings(selectedProjectId);
    setValidationFindings(findings);
  }

  async function handleRunSecretScan() {
    if (!selectedProjectId) {
      return;
    }
    await runSecretScan(selectedProjectId, selectedFileId);
    const findings = await listSecretFindings(selectedProjectId);
    setSecretFindings(findings);
  }

  return (
    <div className="feature-page">
      <header className="feature-header atlas-panel">
        <SectionHeading
          detail="Edit config files through the command rail with diff preview, validation, and snapshot undo. Secret values are always masked in the UI."
          eyebrow="Config"
          title="Edit and validate server configuration"
        />
      </header>

      <Alert severity="info" title="Editor note">
        Monaco editor is not included yet (requires dependency approval). Using a token-styled monospace textarea as a functional placeholder until
        @monaco-editor/react is approved.
      </Alert>

      <Surface className="project-layout" kind="panel" padded={false}>
        <ProjectPicker
          loading={projectsResource.state === "loading"}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onSelect={setSelectedProjectId}
        />

        <section className="project-main">
          {!selectedProjectId ? (
            <EmptyState detail="Select a project to edit configuration files." title="No project" />
          ) : (
            <>
              <Tabs
                activeId={activeTab}
                ariaLabel="Config views"
                tabs={[
                  { id: "editor", label: "Editor" },
                  { id: "findings", label: "Validation" },
                  { id: "secrets", label: "Secret scan" }
                ]}
                onChange={(id) => setActiveTab(id as ConfigTab)}
              />

              {loading ? <LoadingState title="Loading config files" detail="Reading tracked config paths." /> : null}
              {error ? <ErrorState error={error} onRetry={() => bumpMutation()} /> : null}

              {files.length === 0 && !loading ? (
                <EmptyState detail="Rescan config files from the backend or import a project with server.cfg." title="No config files tracked" />
              ) : null}

              {activeTab === "editor" && files.length > 0 ? (
                <div className="workspace-grid">
                  <Surface kind="card">
                    <SectionHeading title="Config files" />
                    <div className="project-list">
                      {files.map((file) => (
                        <button
                          className={file.config_file_id === selectedFileId ? "project-card project-card--active" : "project-card"}
                          key={file.config_file_id}
                          type="button"
                          onClick={() => setSelectedFileId(file.config_file_id)}
                        >
                          <span>
                            <strong>{file.path}</strong>
                            <small>{file.config_type}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  </Surface>

                  {selectedFile && selectedProjectId ? (
                    <Surface className="workspace-panel--wide" kind="card">
                      <CodeEditor
                        label={loadedPath || selectedFile.path}
                        note="Monospace textarea placeholder — Monaco pending approval."
                        value={editorContent}
                        onChange={(event) => setEditorContent(event.target.value)}
                      />
                      {previewDiff ? (
                        <Alert severity="info" title="Preview diff">
                          <pre className="command-json">{previewDiff}</pre>
                        </Alert>
                      ) : null}
                      <CommandPanel
                        description="Preview shows unified diff and validation findings. Execute writes with snapshot undo."
                        executeLabel="Apply change"
                        title="Apply config change"
                        onDryRun={() => dryRunConfigChange(selectedProjectId, selectedFile.config_file_id, editorContent)}
                        onExecute={() => applyConfigChange(selectedProjectId, selectedFile.config_file_id, editorContent)}
                        onPreview={async () => {
                          const preview = await previewConfigChange(selectedProjectId, selectedFile.config_file_id, editorContent);
                          const diff = String(preview.data.preview.diff ?? "");
                          setPreviewDiff(diff || null);
                          return preview;
                        }}
                        onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                        onSuccess={() => bumpMutation()}
                      />
                    </Surface>
                  ) : null}
                </div>
              ) : null}

              {activeTab === "findings" ? (
                <Surface kind="card">
                  <SectionHeading detail="Validation findings from the backend rules engine." title="Validation findings" />
                  <div className="setup-step__actions">
                    <Button variant="primary" onClick={() => void handleRunValidation()}>
                      Run validation
                    </Button>
                  </div>
                  {validationFindings.length === 0 ? (
                    <EmptyState detail="Run validation to check config files against backend rules." title="No findings" />
                  ) : (
                    <div className="atlas-table-wrap">
                      <table className="atlas-table">
                        <thead>
                          <tr>
                            <th>Severity</th>
                            <th>Rule</th>
                            <th>Path</th>
                            <th>Message</th>
                          </tr>
                        </thead>
                        <tbody>
                          {validationFindings.map((finding) => (
                            <tr key={finding.finding_id ?? `${finding.rule_id}-${finding.line}`}>
                              <td>{finding.severity}</td>
                              <td>{finding.rule_id}</td>
                              <td>
                                {finding.path}:{finding.line ?? "?"}
                              </td>
                              <td>{finding.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Surface>
              ) : null}

              {activeTab === "secrets" ? (
                <Surface kind="card">
                  <SectionHeading
                    detail="Secret values are never shown — only secret_type and backend-redacted previews."
                    title="Secret scan findings"
                  />
                  <Alert severity="danger" title="Privacy surface">
                    Atlas displays masked previews only. Never paste or log raw secrets in the UI.
                  </Alert>
                  <div className="setup-step__actions">
                    <Button variant="primary" onClick={() => void handleRunSecretScan()}>
                      Run secret scan
                    </Button>
                  </div>
                  {secretFindings.length === 0 ? (
                    <EmptyState detail="Run a secret scan to detect credentials in config files." title="No secret findings" />
                  ) : (
                    <div className="atlas-table-wrap">
                      <table className="atlas-table">
                        <thead>
                          <tr>
                            <th>Severity</th>
                            <th>Path</th>
                            <th>Finding</th>
                          </tr>
                        </thead>
                        <tbody>
                          {secretFindings.map((finding) => (
                            <tr key={finding.secret_finding_id ?? `${finding.path}-${finding.line}`}>
                              <td>{finding.severity}</td>
                              <td>
                                {finding.path}:{finding.line ?? "?"}
                              </td>
                              <td>{formatMaskedSecret(finding)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Surface>
              ) : null}
            </>
          )}
        </section>
      </Surface>
    </div>
  );
}
