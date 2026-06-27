import type { ProjectSummary } from "../api/project";
import { Button } from "./Button";
import { StatusPill } from "./Badge";
import { SectionHeading } from "./Surface";
import { EmptyState, LoadingState, OnboardingEmptyState } from "./StateViews";

interface ProjectPickerProps {
  projects: ProjectSummary[];
  selectedProjectId: string | null;
  onSelect: (projectId: string) => void;
  loading?: boolean;
  emptyHref?: string;
}

export function ProjectPicker({ projects, selectedProjectId, onSelect, loading, emptyHref = "#/projects" }: ProjectPickerProps) {
  if (loading) {
    return <LoadingState title="Loading projects" detail="Reading workspace list." />;
  }

  if (projects.length === 0) {
    return (
      <OnboardingEmptyState
        detail="Import or open a project first, then return here to manage resources, git, or config."
        primaryAction={
          <Button variant="primary" onClick={() => (window.location.hash = emptyHref.replace(/^#/, ""))}>
            Go to Projects
          </Button>
        }
        title="No project selected"
      />
    );
  }

  return (
    <section className="project-sidebar">
      <SectionHeading detail="Feature actions run in project context." title="Project" />
      <div className="project-list">
        {projects.map((project) => (
          <button
            className={project.project_id === selectedProjectId ? "project-card project-card--active" : "project-card"}
            key={project.project_id}
            type="button"
            onClick={() => onSelect(project.project_id)}
          >
            <span>
              <strong>{project.display_name}</strong>
              <small>{project.slug}</small>
            </span>
            <StatusPill status={project.status.toLowerCase() === "open" ? "running" : "idle"}>{project.status}</StatusPill>
          </button>
        ))}
      </div>
    </section>
  );
}

export function ProjectPickerEmpty({ title, detail }: { title: string; detail: string }) {
  return <EmptyState detail={detail} title={title} />;
}
