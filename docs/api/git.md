# Git API Contract

Responsibility: repository discovery, clone, fetch/pull, refs, status snapshots, diffs, commit metadata, and Git operation audit. The core contract is provider-neutral and must not assume GitHub.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `DiscoverGitRepositories` | `project_id`, path filters | repository delta | `ProjectScopeViolation`, `ExternalAdapterFailed` | Read scan. | Detect local modifications |
| `CloneRepository` | `project_id`, remote URL, destination, role, `idempotency_key` | `command_plan_id` or operation id | `ValidationFailed`, `PermissionDenied`, `Conflict` | Preview-first if destination changes files. | Clone repositories |
| `FetchRepository` | `project_id`, `git_repository_id`, `idempotency_key` | operation id | `NotFound`, `ExternalAdapterFailed` | Long-running; records operation. | Pull updates |
| `PullRepository` | `project_id`, repo id, strategy, `idempotency_key` | operation id, conflict warnings | `Conflict`, `ExternalAdapterFailed` | Requires clean/approved dirty handling. | Pull updates |
| `CheckoutRef` | `project_id`, repo id, ref, dirty behavior | command plan or summary | `Conflict`, `PermissionDenied` | Preview dirty worktree decisions. | Manage branches |
| `CreateCommit` | `project_id`, repo id, selected paths, message | commit summary | `ValidationFailed`, `Conflict` | Audited; no automatic commits by default. | Commit changes |
| `CaptureGitStatusSnapshot` | `project_id`, repo id | status snapshot id | `NotFound`, `ExternalAdapterFailed` | Read command that persists snapshot. | Incident/backup Git context |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListGitRepositories` | `project_id`, role filters | repo summaries | `ProjectScopeViolation` | Built-in Git support |
| `GetGitRepository` | `project_id`, repo id | repo detail | `NotFound` | Repository detail |
| `ListRefs` | `project_id`, repo id, ref type | refs | `NotFound` | Manage branches |
| `GetWorktreeStatus` | `project_id`, repo id | current status | `NotFound`, `ExternalAdapterFailed` | Detect modifications |
| `GetDiffSummary` | `project_id`, repo id, base/head/path filters | diff summary | `NotFound` | Compare commits |
| `ListGitOperations` | `project_id`, repo id, filters | operation history | `ProjectScopeViolation` | Transparent Git operations |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `GitRepositoryDiscovered` | `project_id`, repo id, role | Resources, Audit |
| `GitStatusSnapshotCaptured` | `project_id`, repo id, dirty state | Incident, Backup |
| `GitOperationStarted` | `project_id`, repo id, operation type | Automation, Audit |
| `GitOperationCompleted` | `project_id`, repo id, status, commit/ref | Resources, Config, Automation, Incident |
| `GitCommitCreated` | `project_id`, repo id, commit sha | Incident, Backup, Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ProjectImported` | Discover project and resource repos | Populate Git inventory. |
| `ResourceInstalled` | Link resource to Git repo when relevant | Source provenance. |
| `ResourceUpdated` | Capture status after resource update | Incident/rollback context. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `GitRepositoryPort` | Persist repos, refs, commits, status, operations | Requires `project_id` | `persistence` |
| `GitProviderPort` | Execute Git operations through approved local adapter | Requires `project_id` and repo path allowlist | `git` |
| `FilesystemSafetyPort` | Validate destination/path ownership | Requires project path allowlist | `filesystem` |
| `AuditPort` | Record Git operations | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/git/repositories` | filters | repository list |
| `POST /api/v1/projects/{project_id}/git/discover` | path filters | discovery result |
| `GET /api/v1/projects/{project_id}/git/repositories/{repo_id}/status` | ids | status summary |
| `POST /api/v1/projects/{project_id}/git/repositories/{repo_id}/pull-plan` | strategy | command plan |
| `POST /api/v1/projects/{project_id}/git/repositories/{repo_id}/pull` | approved plan | operation id |
| `GET /api/v1/projects/{project_id}/git/repositories/{repo_id}/diff` | base/head/path filters | diff summary |
| `POST /api/v1/projects/{project_id}/git/repositories/{repo_id}/commits` | selected paths, message | commit summary |

## Open Questions

- Whether commit author metadata should be redacted or hashed by default.

## Deviations

None.
