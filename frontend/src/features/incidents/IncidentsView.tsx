import { useCallback, useEffect, useMemo, useState } from "react";

import { listProjects, type ProjectSummary } from "../../api/project";
import {
  compareIncidents,
  exportIncidentMarkdown,
  getIncident,
  getOccurrenceTimeline,
  listIncidents,
  type ContextSnapshot,
  type IncidentCompareResult,
  type IncidentGroup,
  type IncidentGroupDetail,
  type OccurrenceTimeline
} from "../../api/incident";
import {
  Alert,
  Badge,
  Button,
  CodeEditor,
  DefinitionGrid,
  ProjectPicker,
  SectionHeading,
  StatusPill,
  Surface,
  Table,
  Tabs,
  Toast,
  type StatusKind
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";
import { useBackendStatus } from "../../app/useBackendStatus";

type IncidentTab = "timeline" | "snapshot" | "related" | "compare" | "export";

function severityKind(severity: string): StatusKind {
  if (severity === "critical" || severity === "error") {
    return "crashed";
  }
  if (severity === "warn" || severity === "warning") {
    return "pending";
  }
  return "idle";
}

function formatContextLabel(contextType: string): string {
  return contextType.replace(/_/g, " ");
}

function SnapshotPanel({ snapshots }: { snapshots: ContextSnapshot[] }) {
  if (snapshots.length === 0) {
    return <EmptyState title="No snapshot data" detail="This occurrence has no captured context snapshots." />;
  }

  return (
    <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
      <Alert severity="info" title="Backend-sanitized snapshot">
        Atlas stores redacted and masked values server-side (e.g. git remotes, config secrets). Displayed exactly as returned — never un-redacted in the UI.
      </Alert>
      {snapshots.map((snapshot) => (
        <Surface key={snapshot.context_snapshot_id} kind="well">
          <div className="atlas-row" style={{ justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
            <strong>{formatContextLabel(snapshot.context_type)}</strong>
            <Badge variant={snapshot.redaction_state === "redacted" ? "warn" : "neutral"}>{snapshot.redaction_state}</Badge>
          </div>
          <pre className="atlas-code-block">{JSON.stringify(snapshot.snapshot_json, null, 2)}</pre>
        </Surface>
      ))}
    </div>
  );
}

export function IncidentsView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [groups, setGroups] = useState<IncidentGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentGroupDetail | null>(null);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState<string | null>(null);
  const [occurrenceTimeline, setOccurrenceTimeline] = useState<OccurrenceTimeline | null>(null);
  const [activeTab, setActiveTab] = useState<IncidentTab>("timeline");
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<IncidentCompareResult | null>(null);
  const [exportMarkdown, setExportMarkdown] = useState<string | null>(null);
  const [exportSummary, setExportSummary] = useState<Record<string, unknown> | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  const reloadGroups = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rows = await listIncidents(selectedProjectId);
      setGroups(rows);
      if (!selectedGroupId && rows.length > 0) {
        setSelectedGroupId(rows[0].incident_group_id);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, selectedGroupId]);

  useEffect(() => {
    void reloadGroups();
  }, [reloadGroups]);

  const loadDetail = useCallback(async () => {
    if (!selectedProjectId || !selectedGroupId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setError(null);
    try {
      const groupDetail = await getIncident(selectedProjectId, selectedGroupId);
      setDetail(groupDetail);
      const occurrenceId = groupDetail.occurrences[0]?.occurrence_id ?? null;
      setSelectedOccurrenceId(occurrenceId);
      if (occurrenceId) {
        const timeline = await getOccurrenceTimeline(selectedProjectId, occurrenceId);
        setOccurrenceTimeline(timeline);
      } else {
        setOccurrenceTimeline(null);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setDetailLoading(false);
    }
  }, [selectedProjectId, selectedGroupId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  async function loadOccurrenceTimeline(occurrenceId: string) {
    if (!selectedProjectId) {
      return;
    }
    setSelectedOccurrenceId(occurrenceId);
    try {
      const timeline = await getOccurrenceTimeline(selectedProjectId, occurrenceId);
      setOccurrenceTimeline(timeline);
    } catch (caught) {
      setError(caught);
    }
  }

  function toggleCompareSelection(groupId: string) {
    setCompareSelection((current) => (current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId]));
  }

  async function handleCompare() {
    if (!selectedProjectId || compareSelection.length < 2) {
      return;
    }
    setCompareBusy(true);
    try {
      const result = await compareIncidents(selectedProjectId, compareSelection);
      setCompareResult(result);
      setActiveTab("compare");
    } catch (caught) {
      setError(caught);
    } finally {
      setCompareBusy(false);
    }
  }

  async function handleExport() {
    if (!selectedProjectId || !selectedGroupId) {
      return;
    }
    setExportBusy(true);
    setExportMarkdown(null);
    setExportSummary(null);
    try {
      const result = await exportIncidentMarkdown(selectedProjectId, selectedGroupId, selectedOccurrenceId);
      setExportMarkdown(result.markdown);
      setExportSummary(result.redaction_summary as Record<string, unknown>);
      setActiveTab("export");
      setToast("Sanitized Markdown ready — review before copying to external services.");
    } catch (caught) {
      setError(caught);
    } finally {
      setExportBusy(false);
    }
  }

  async function copyExport() {
    if (!exportMarkdown) {
      return;
    }
    try {
      await navigator.clipboard.writeText(exportMarkdown);
      setToast("Copied to clipboard — paste manually where you need it.");
    } catch {
      setToast("Copy failed — select and copy from the editor manually.");
    }
  }

  const fingerprintHint = useMemo(() => {
    if (!detail?.fingerprint_components) {
      return null;
    }
    return JSON.stringify(detail.fingerprint_components, null, 2);
  }, [detail]);

  if (backendStatus.state !== "ready") {
    return <LoadingState title="Waiting for backend" detail="Incident intelligence requires a connected Atlas backend." />;
  }

  if (projectsResource.state === "loading") {
    return <LoadingState title="Loading projects" detail="Fetching workspace list for incident context." />;
  }

  if (projects.length === 0) {
    return <EmptyState title="No projects yet" detail="Import a project before reviewing incident groups and snapshots." />;
  }

  return (
    <div className="atlas-feature">
      {toast ? (
        <Toast severity="info" title="Incidents" onDismiss={() => setToast(null)}>
          {toast}
        </Toast>
      ) : null}

      <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <SectionHeading eyebrow="Operate" title="Incidents" detail="Fingerprint-grouped crashes with environment snapshots and sanitized export." />
        <ProjectPicker projects={projects} selectedProjectId={selectedProjectId} onSelect={setSelectedProjectId} />
      </div>

      <Alert severity="info" title="Grouping caveat (M7b)">
        Incidents are grouped by fingerprint — similar crashes may merge. Use per-occurrence messages, fingerprint components, and compare to spot accidental over-grouping.
      </Alert>

      {error ? <ErrorState error={error} /> : null}

      <div className="atlas-row" style={{ alignItems: "flex-start", gap: "var(--space-4)", flexWrap: "wrap" }}>
        <Surface kind="panel" style={{ flex: "1 1 320px", minWidth: "280px" }}>
          <SectionHeading title="Incident groups" detail={`${groups.length} grouped issue(s)`} />
          {loading ? <LoadingState title="Loading incidents" detail="Reading grouped incident records." /> : null}
          {!loading && groups.length === 0 ? (
            <EmptyState title="No incidents captured" detail="Server crashes and signals will appear here once M7 capture runs." />
          ) : null}
          {!loading && groups.length > 0 ? (
            <Table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Count</th>
                  <th>Severity</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr
                    key={group.incident_group_id}
                    className={group.incident_group_id === selectedGroupId ? "atlas-table__row--selected" : undefined}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelectedGroupId(group.incident_group_id)}
                  >
                    <td>
                      <strong>{group.title}</strong>
                      <p className="muted-copy">{group.category}</p>
                    </td>
                    <td>{group.occurrence_count}</td>
                    <td>
                      <StatusPill status={severityKind(group.severity)}>{group.severity}</StatusPill>
                    </td>
                    <td>{new Date(group.last_seen_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : null}
        </Surface>

        <Surface kind="panel" style={{ flex: "2 1 480px", minWidth: "320px" }}>
          {!selectedGroupId || !detail ? (
            detailLoading ? (
              <LoadingState title="Loading group detail" detail="Fetching occurrences, fingerprint, and related groups." />
            ) : (
              <EmptyState title="Select an incident group" detail="Choose a group to inspect timeline, snapshots, and export." />
            )
          ) : (
            <>
              <SectionHeading title={detail.title} detail={`${detail.occurrence_count} occurrence(s) · ${detail.status}`} />
              <DefinitionGrid
                items={[
                  ["Severity", detail.severity],
                  ["Category", detail.category],
                  ["First seen", new Date(detail.first_seen_at).toLocaleString()],
                  ["Last seen", new Date(detail.last_seen_at).toLocaleString()],
                  ["Fingerprint", <code key="fp">{detail.fingerprint.slice(0, 16)}…</code>]
                ]}
              />
              {fingerprintHint ? (
                <details style={{ marginTop: "var(--space-3)" }}>
                  <summary>Fingerprint components (spot over-grouping)</summary>
                  <pre className="atlas-code-block">{fingerprintHint}</pre>
                </details>
              ) : null}

              <Tabs
                activeId={activeTab}
                ariaLabel="Incident detail views"
                tabs={[
                  { id: "timeline", label: "Timeline" },
                  { id: "snapshot", label: "Snapshot" },
                  { id: "related", label: "Related" },
                  { id: "compare", label: "Compare" },
                  { id: "export", label: "Export" }
                ]}
                onChange={(id) => setActiveTab(id as IncidentTab)}
              />

              {activeTab === "timeline" ? (
                <Table>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Source</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.occurrences.map((occurrence) => (
                      <tr
                        key={occurrence.occurrence_id}
                        className={occurrence.occurrence_id === selectedOccurrenceId ? "atlas-table__row--selected" : undefined}
                        style={{ cursor: "pointer" }}
                        onClick={() => void loadOccurrenceTimeline(occurrence.occurrence_id)}
                      >
                        <td>{new Date(occurrence.occurred_at).toLocaleString()}</td>
                        <td>{occurrence.source_type}</td>
                        <td>{occurrence.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : null}

              {activeTab === "snapshot" ? (
                occurrenceTimeline ? (
                  <SnapshotPanel snapshots={occurrenceTimeline.context_snapshots} />
                ) : (
                  <EmptyState title="Select an occurrence" detail="Pick a timeline row to view its environment snapshot." />
                )
              ) : null}

              {activeTab === "related" ? (
                detail.related_groups.length === 0 ? (
                  <EmptyState title="No related groups" detail="Related incident links appear when the backend detects relationships." />
                ) : (
                  <Table>
                    <thead>
                      <tr>
                        <th>Relation</th>
                        <th>Target group</th>
                        <th>Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.related_groups.map((related, index) => (
                        <tr key={String(related.related_group_id ?? index)}>
                          <td>{String(related.relation_type ?? "related")}</td>
                          <td>{String(related.target_group_id ?? related.related_group_id ?? "—")}</td>
                          <td>{related.confidence != null ? String(related.confidence) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )
              ) : null}

              {activeTab === "compare" ? (
                <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>
                  <p className="muted-copy">Select two or more groups from the list (checkboxes below), then compare fingerprints and fields.</p>
                  {groups.map((group) => (
                    <label key={group.incident_group_id} className="atlas-row" style={{ gap: "var(--space-2)" }}>
                      <input
                        checked={compareSelection.includes(group.incident_group_id)}
                        type="checkbox"
                        onChange={() => toggleCompareSelection(group.incident_group_id)}
                      />
                      <span>{group.title}</span>
                    </label>
                  ))}
                  <Button disabled={compareSelection.length < 2} loading={compareBusy} variant="secondary" onClick={() => void handleCompare()}>
                    Compare selected
                  </Button>
                  {compareResult ? (
                    <>
                      <DefinitionGrid items={[["Shared fingerprint", compareResult.shared.fingerprint ? "Yes" : "No"]]} />
                      {compareResult.differences.length === 0 ? (
                        <p className="muted-copy">No field differences detected across selected groups.</p>
                      ) : (
                        <pre className="atlas-code-block">{JSON.stringify(compareResult.differences, null, 2)}</pre>
                      )}
                    </>
                  ) : null}
                </div>
              ) : null}

              {activeTab === "export" ? (
                <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>

                  <p className="muted-copy">
                    Export is functional and sanitized. There is no AI integration — you copy the Markdown manually after reviewing it.
                  </p>
                  <Button loading={exportBusy} variant="primary" onClick={() => void handleExport()}>
                    Generate sanitized Markdown export
                  </Button>
                  {exportSummary ? (
                    <DefinitionGrid
                      items={[
                        ["Redactions applied", String(exportSummary.redaction_count ?? 0)],
                        ["Policy", String(exportSummary.policy ?? "redact_in_place")],
                        ["Backend note", String(exportSummary.note ?? "—")]
                      ]}
                    />
                  ) : null}
                  {exportMarkdown ? (
                    <>
                      <CodeEditor label="Sanitized Markdown (manual copy only)" readOnly rows={16} value={exportMarkdown} />
                      <Button variant="secondary" onClick={() => void copyExport()}>
                        Copy to clipboard
                      </Button>
                    </>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </Surface>
      </div>
    </div>
  );
}
