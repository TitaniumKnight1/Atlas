# Git Schema

Feature traceability: clone repositories, branches, commits, pull updates, local modifications, compare commits, and incident/backup association with Git state.

## Tables

### `git_repositories`

| Column | Type | Notes |
| --- | --- | --- |
| `git_repository_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `local_path` | `TEXT` | Required normalized path. |
| `remote_url` | `TEXT` | Nullable. |
| `default_branch` | `TEXT` | Nullable. |
| `repository_role` | `TEXT` | Required: `project`, `resource`, `template`, `unknown`. |
| `resource_id` | `TEXT` | Nullable FK to `resources`. |
| `last_scanned_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `git_repository_id`; unique `(project_id, local_path)`.
Indexes: `idx_git_repositories_project_role(project_id, repository_role)`.
Lifecycle: current repository inventory; deleted repos marked through status snapshots.
Rationale: captures all Git roots Atlas knows about without assuming GitHub.

### `git_refs`

| Column | Type | Notes |
| --- | --- | --- |
| `git_ref_id` | `TEXT` | Primary key. |
| `git_repository_id` | `TEXT` | Required FK to `git_repositories`. |
| `ref_name` | `TEXT` | Required. |
| `ref_type` | `TEXT` | Required: `branch`, `tag`, `remote`. |
| `commit_sha` | `TEXT` | Nullable. |
| `is_current` | `INTEGER` | Boolean 0/1. |
| `detected_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `git_ref_id`; unique `(git_repository_id, ref_name, ref_type)`.
Indexes: `idx_git_refs_repo_current(git_repository_id, is_current)`.
Lifecycle: refreshed on scan/fetch.
Rationale: powers branch display and compare workflows.

### `git_commits`

| Column | Type | Notes |
| --- | --- | --- |
| `git_commit_id` | `TEXT` | Primary key. |
| `git_repository_id` | `TEXT` | Required FK to `git_repositories`. |
| `commit_sha` | `TEXT` | Required. |
| `parent_shas_json` | `JSON` | Nullable parent SHA list. |
| `author_name` | `TEXT` | Nullable. |
| `author_email_hash` | `TEXT` | Nullable privacy-preserving hash. |
| `committed_at` | `TEXT` | Nullable UTC timestamp. |
| `message_summary` | `TEXT` | Nullable. |

Keys and constraints: PK `git_commit_id`; unique `(git_repository_id, commit_sha)`.
Indexes: `idx_git_commits_repo_time(git_repository_id, committed_at)`.
Lifecycle: cache metadata; can prune commits not referenced by incidents/backups.
Rationale: links runtime failures, backups, and resource versions to code state.

### `git_worktree_status_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `git_status_snapshot_id` | `TEXT` | Primary key. |
| `git_repository_id` | `TEXT` | Required FK to `git_repositories`. |
| `head_commit_sha` | `TEXT` | Nullable. |
| `branch_name` | `TEXT` | Nullable. |
| `is_dirty` | `INTEGER` | Boolean 0/1. |
| `ahead_count` | `INTEGER` | Nullable. |
| `behind_count` | `INTEGER` | Nullable. |
| `captured_at` | `TEXT` | Required UTC timestamp. |
| `summary_json` | `JSON` | Nullable. |

Keys and constraints: PK `git_status_snapshot_id`; check `is_dirty in (0,1)`.
Indexes: `idx_git_status_repo_time(git_repository_id, captured_at)`, `idx_git_status_dirty(is_dirty, captured_at)`.
Lifecycle: retain snapshots referenced by incidents/backups; prune old unreferenced snapshots.
Rationale: captures dirty state at incident and command time.

### `git_file_changes`

| Column | Type | Notes |
| --- | --- | --- |
| `git_file_change_id` | `TEXT` | Primary key. |
| `git_status_snapshot_id` | `TEXT` | Required FK to `git_worktree_status_snapshots`. |
| `path` | `TEXT` | Required repo-relative path. |
| `change_status` | `TEXT` | Required: `added`, `modified`, `deleted`, `renamed`, `untracked`. |
| `old_path` | `TEXT` | Nullable for renames. |
| `insertions` | `INTEGER` | Nullable. |
| `deletions` | `INTEGER` | Nullable. |

Keys and constraints: PK `git_file_change_id`; unique `(git_status_snapshot_id, path)`.
Indexes: `idx_git_file_changes_status(change_status)`.
Lifecycle: follows parent snapshot.
Rationale: supports diff previews and incident Git context without storing full diffs by default.

### `git_operations`

| Column | Type | Notes |
| --- | --- | --- |
| `git_operation_id` | `TEXT` | Primary key. |
| `git_repository_id` | `TEXT` | Required FK to `git_repositories`. |
| `operation_type` | `TEXT` | Required: `clone`, `fetch`, `pull`, `checkout`, `commit`, `diff`, `status`. |
| `status` | `TEXT` | Required: `planned`, `running`, `succeeded`, `failed`, `cancelled`. |
| `command_execution_id` | `TEXT` | Nullable FK to `command_executions`. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `result_json` | `JSON` | Nullable sanitized command result. |

Keys and constraints: PK `git_operation_id`; check `operation_type`; check `status`.
Indexes: `idx_git_operations_repo_time(git_repository_id, started_at)`, `idx_git_operations_status(status)`.
Lifecycle: audit-style retention; large outputs stored externally only if needed.
Rationale: makes Git automation transparent.

## Open Questions

- Whether commit author email should always be hashed or stored only when user opts in.
- Whether full patch contents belong in SQLite or only local files referenced by `local_files`.

## Deviations

None.
