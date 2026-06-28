# ADR-0027: Pathway 2 Dev/Prod Config Separation Model

## Status

Accepted

## Context

**Pathway 2** is the Atlas workflow where a developer clones a team's production FiveM server repository, runs a **safe local dev build** (no production secrets at runtime, machine-specific ports/paths), and pushes work back on a branch **without** leaking secrets or overwriting production configuration.

Discovery (Pathway 2 read-only pass) identified two open dangers that all Pathway 2 milestones must close:

1. **Inbound:** A new developer clones a repo whose committed `server.cfg` still contains production license keys, database connection strings, and API tokens. Today Atlas **detects** and **masks** secrets (M4a / ADR-0009) but does not **substitute** them. Nothing blocks starting FXServer with production credentials locally.
2. **Outbound:** Config is a **single on-disk file** edited and committed together. If a developer substitutes dev values in place, a commit (and any future push) can overwrite production config or leak dev credentials. M4b has local commit but **no push** (ADR-0010).

This ADR records **PHASE 1 research** into current FXServer `server.cfg` mechanics and selects the **dev/prod separation model** that P2-1 through P2-5 will implement. It is the foundation decision; it does not implement features.

Related: ADR-0009 (config editor + secret scan), ADR-0010 (git integration, no implicit push), `docs/standards/configuration-strategy.md`.

---

## PHASE 1 Research — FXServer `exec` and overlay semantics

Research used current Cfx.re/FiveM documentation and community patterns (June 2026). Behavior below is **research-backed**; items marked **partial** need validation on target artifact builds during P2-1.

### 1. Does `server.cfg` support `exec` to include/layer another file?

**Yes.**

The official Server Commands reference defines:

> **`exec [filename]`** — Runs the commands specified in the filename, relative to the server data directory, or any resource name specified with `@`.

Examples from the same page: `exec server_nested.cfg`, `exec @vMenu/config/permissions.cfg`.

Source: [Server Commands — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/server-commands/#exec-filename)

The vanilla FXServer setup guide ships an example `server.cfg` with a commented nested-config hook:

```
# Nested configs!
#exec server_internal.cfg
```

Source: [Setting up a Vanilla FXServer — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/setting-up-a-server-vanilla/)

**Load order:** `server.cfg` is processed sequentially. When the parser reaches `exec other.cfg`, commands in `other.cfg` run **at that point** in the stream. An `exec` placed **at the end** of `server.cfg` therefore runs after all preceding lines.

### 2. Can a later `exec`'d file override convars/settings set earlier?

**Mostly yes for convars; partial for non-convar commands.**

**Convars (`set`, `sets`, and direct convar assignment lines such as `sv_licenseKey`, `sv_maxclients`):**

The official Convars reference documents `set convar_name convar_value` as the standard assignment mechanism. Re-assigning a convar replaces its value for subsequent readers (standard FXServer console semantics). Community operators routinely split environment-specific values into nested files loaded via `exec` (e.g. per-server `s1.cfg` for ports, hostname, slots) or apply `+set` on the startup command line **after** `+exec server.cfg` to override cfg values.

Sources:

- [Convars — Cfx.re Docs](https://docs.fivem.net/docs/scripting-reference/convars/)
- [Server host name — Cfx.re Community](https://forum.cfx.re/t/server-host-name/243374) (nested cfg / `+set` override patterns)

**Therefore:** If `server.cfg` ends with `exec server.cfg.local`, values in `server.cfg.local` **override** the same convars set earlier in `server.cfg` for settings Pathway 2 cares about: `sv_licenseKey`, `sv_hostname`, `sv_maxclients`, `set mysql_connection_string "…"`, custom script convars, and `sets` metadata lines.

**`endpoint_add_tcp` / `endpoint_add_udp` — PARTIAL:**

These are **server commands**, not convars. The official docs describe them as creating/binding endpoint instances; they are not readable via `GetConvar` (see [citizenfx/fivem#1839](https://github.com/citizenfx/fivem/issues/1839)). Official proxy documentation instructs operators to **edit** endpoint lines in place rather than rely on a second additive override. Duplicate endpoint declarations are ambiguous; Atlas's own validator already warns on duplicate `endpoint_add_tcp` ports.

Sources:

- [Server Commands — endpoint_add_tcp / endpoint_add_udp](https://docs.fivem.net/docs/server-manual/server-commands/)
- [Proxy Setup — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/proxy-setup/) (endpoint ordering: `endpoint_add_udp` before `endpoint_add_tcp`)

**Pathway 2 implication:** Dev port overrides belong in `server.cfg.local`, and **adopt-time normalization must remove or relocate** `endpoint_add_*` lines from the committed base — not duplicate them in base and overlay.

**`ensure` / `start` / `stop` — PARTIAL:**

Resource startup commands executed in the base file have already run when a trailing `exec` is processed. A later `exec` can **add** ensures but cannot retroactively un-start resources from the base. For Pathway 2, treat the **committed base** as canonical for shared resource load order; use the overlay for secrets, endpoints, slots, hostname, and dev convars — not for restructuring the production resource graph.

**`onesync` and similar — EXCEPTION (flagged):**

Community reports indicate some builds restrict `onesync` to startup command-line `+set` in certain configurations. Pathway 2 dev-transform must treat `onesync` as **build-dependent**: prefer leaving base values untouched unless validated on the target artifact channel.

Source: [How to start onesync on server — Cfx.re Community](https://forum.cfx.re/t/how-to-start-onesync-on-server/1601351)

### 3. Can secrets (`sv_licenseKey`, DB/API convars) live in an exec'd overlay?

**Yes for convar-form secrets.**

- `sv_licenseKey` is set as a standard server convar in the vanilla example (`sv_licenseKey changeme`).
- Database and script credentials are conventionally `set mysql_connection_string "…"` or custom `set myResource_*` convars.

An overlay loaded **after** the base can assign dev license keys and connection strings that **replace** production values for local runtime. The base should hold **non-secret placeholders** (e.g. `CHANGE_ME` / `USE_LOCAL_OVERLAY`) after inbound normalization so production secrets are not required in the committed file on the dev machine.

**Not viable:** Treating `server.cfg` as a Lua/script file (e.g. `sv_licenseKey GetConvar(…)`) — community attempts failed; license keys are not loaded that way.

Source: [Load convar from server.cfg — Cfx.re Community](https://forum.cfx.re/t/load-convar-from-server-cfg/2847587)

### 4. Practical team patterns today

| Pattern | Description | Source |
| --- | --- | --- |
| **Nested `exec` splits** | `server.cfg` stays thin; `exec permissions.cfg`, `exec resources.cfg` hold ACLs and ensures | [WildFyr server.cfg guide](https://docs.wildfyr.net/c/fivem/servercfg), [Nights Software ACE docs](https://docs.nights-software.com/resources/acePerms/) |
| **Resource `@` exec** | `exec @resource/config.cfg` for per-resource overrides | [Server Commands](https://docs.fivem.net/docs/server-manual/server-commands/), [Convar vs config.lua — Cfx.re Community](https://forum.cfx.re/t/convar-vs-config-lua/5222943) |
| **Gitignored env + cfg** | `.env` / secret files out of git; Docker setups mount secrets and `exec` relative cfg paths | [itsxScrubz/fivem-docker](https://github.com/itsxScrubz/fivem-docker) |
| **Startup `+set` for secrets** | Keep public `server.cfg`; pass `+set sv_licenseKey …` on launch | [Load convar from server.cfg — Cfx.re Community](https://forum.cfx.re/t/load-convar-from-server-cfg/2847587) |

**Research verdict:** `exec` overlay with **last-write-wins convar override** is **supported and commonly used**. It is **partial** for `endpoint_add_*` (relocate, don't duplicate) and resource `ensure` ordering (base stays canonical). Overlay-dependent Model 1 is **viable** with adopt-time normalization rules documented below.

---

## Decision

Adopt **Model 1 — Local overlay** (`server.cfg` + gitignored `server.cfg.local`), with **adopt-time base normalization** for commands that do not override cleanly.

### File layout

| File | Git | Role |
| --- | --- | --- |
| `server.cfg` | **Tracked** | Team-canonical shared config: resource ensures, framework settings, ACL structure. After Pathway 2 inbound: **placeholders only** for secrets; `endpoint_add_*` either absent or commented with pointer to overlay; **must** end with `exec server.cfg.local`. |
| `server.cfg.local` | **Gitignored** | Machine-local overlay: dev/prod license key, DB/API convars, `endpoint_add_udp` + `endpoint_add_tcp` (UDP before TCP), `sv_maxclients`, `sv_hostname`, dev-only convars. Created/populated by P2-2/P2-3; never committed. |
| `server.cfg.local.example` | **Tracked** (optional) | Documented template with `CHANGE_ME` values — no real secrets. |

**Atlas-managed `.gitignore` entry** (P2-4): `server.cfg.local` (and optionally `secrets.cfg.local` if teams split further — default is single overlay file).

### Why Model 1 (not 2 or 3)

| Model | Assessment |
| --- | --- |
| **Model 1 — Local overlay** | Matches official `exec` + community nested-cfg practice. Convar secrets and dev tuning override at runtime via trailing `exec`. Return-path safety: overlay is **gitignored** → dev values **cannot** be pushed. Base edits are limited to placeholders + `exec` trailer → safe to merge. Contamination is **structurally impossible** for overlay contents; base secret contamination is closed by inbound normalization (placeholders in tracked file, real values only in local). |
| **Model 2 — Gitignored secrets file only** | Strict subset of Model 1. Insufficient alone: dev ports, hostname, and slots also need local override; would still require a second file or in-place edits. |
| **Model 3 — In-place substitution + commit guards** | Always buildable but **guard-dependent**. A single committed `server.cfg` with substituted dev values can be staged accidentally; fail-open risk is incompatible with Atlas fail-closed posture. Use only as **defense-in-depth** (P2-4 pre-commit scan), not as the primary separation model. |

**Principle:** Prefer making contamination **structurally impossible** (gitignored overlay + placeholder base) over hoping guards catch mistakes. Guards remain mandatory backup (ADR-0009 secret vocabulary on staged files).

### Inbound normalization (required for Model 1)

When adopting a production repo whose `server.cfg` still contains inline secrets (typical today):

1. **Extract** detected secrets and machine-specific settings from `server.cfg` into `server.cfg.local` (P2-2 substitution target is the **overlay**, not only in-place rewrite).
2. **Replace** extracted secret lines in `server.cfg` with documented placeholders (`CHANGE_ME` / `USE_LOCAL_OVERLAY`).
3. **Relocate** `endpoint_add_*` lines to `server.cfg.local` (remove from base) per partial-override research.
4. **Append** `exec server.cfg.local` if missing (idempotent).
5. **Record** undo snapshots per ADR-0009.

Production hosts continue using their own gitignored `server.cfg.local` with production secrets; the committed base converges on a **secret-free, overlay-referenced** shape teams can merge once.

### Return-path safety

- **Structurally:** `server.cfg.local` is gitignored → never in `git add -A` if ignore rules are applied.
- **Defense-in-depth (P2-4):** Pre-commit preview runs M4a secret scan on staged paths; **fail closed** if `server.cfg` (or other tracked cfg) matches `SECRET_RULES` or contains non-placeholder license/connection patterns. Default commit scope for Pathway 2 projects should **exclude** `server.cfg` unless the change is an approved team migration (exec trailer + placeholders only).
- **Push sub-decision (flagged):** ADR-0010 prohibits implicit push. Pathway 2 **will likely require** an explicit, preview-first `PushBranch` in P2-4 with the same staged-file gates. **This ADR does not amend ADR-0010**; P2-4 must either add a superseding ADR amendment or remain **commit-only** with push performed outside Atlas under team policy. **Default until P2-4:** commit-only inside Atlas; push sub-decision deferred.

### Privacy boundary

Substitution and overlay materialization **read production secret values from the local working tree** to populate `server.cfg.local` and to replace inline secrets with placeholders in `server.cfg`. This is **local FiveM project data** (M2 boundary):

- Raw secrets **must not** appear in telemetry, SSE, audit persistence, or command previews.
- Extend ADR-0009 redaction to **diff/preview payloads** for Pathway 2 commands (same `SECRET_RULES` / `redacted_preview` pattern).
- Undo snapshots may hold prior file content on disk in Atlas snapshot stores — already true for M4a; Pathway 2 does not change the privacy class.
- Pathway 2 undo retains **local-only pre-image snapshots** under Atlas app-data (`pathway2-undo/`); these may contain secret-bearing prior config for normalization/substitution undo. They are never committed, never sent to telemetry, and follow the same local-copy posture as M8c backups — a deliberate, documented property.

---

## Consequences by Pathway 2 milestone

### P2-1 — Adopt existing repo

- Detect `server.cfg`, `resources/`, `txData`, artifacts; verify trailing `exec server.cfg.local` or plan to add it.
- Clone → import → structure report; **do not** auto-start until overlay status is known.
- Flag repos whose `server.cfg` has inline secrets and no gitignored overlay yet.

### P2-2 — Secret substitution

- **Target file:** `server.cfg.local` (create if missing).
- **Source:** scan `server.cfg` (and nested exec'd cfgs if tracked); move secrets to overlay; write placeholders to base.
- Block or warn on `startProcess` until substitution complete or user explicitly accepts risk (fail-closed default).

### P2-3 — Dev config transform

- Apply dev transforms to **`server.cfg.local`**: ports (`endpoint_add_*` with UDP-before-TCP), `sv_maxclients`, `sv_hostname`, dev convars.
- **Do not** duplicate `endpoint_add_*` in base.
- Leave base `ensure` list unchanged unless team explicitly opts into resource diff.

### P2-4 — Return-path safety (implemented)

- **Primary defense (Model 1):** `server.cfg.local` is gitignored; base `server.cfg` holds placeholders only after P2-1/P2-2.
- **Defense-in-depth:** `evaluate_commit_safety()` scans the explicit staged path set with M4a `SECRET_RULES` plus pathway2 checks (overlay never committable; base `server.cfg` placeholders only). **Fail-closed** — blocked commits cannot proceed.
- **Commit-only (ADR-0010 upheld):** Atlas performs explicit-path local commits only; **no push**. After a safe commit, devs push manually with their git tool.
- **Push seam:** The same `evaluate_commit_safety()` gate is the documented reusable entry point for a future guarded `PushBranch` if ADR-0010 is later amended. Push is not implemented in P2-4.

### P2-5 — Join-team wizard

- Second flow distinct from greenfield Setup (M3a).
- Steps: clone/import → structure → substitute secrets to overlay → dev transform → validate → optional run.
- Skip artifact install and `server.cfg` **generation**; reuse dependency validation and resource inventory.
- Environment profile `local` links to overlay path and transform presets (Atlas metadata per `configuration-strategy.md`).

### Config schema / Atlas metadata

- Track overlay path (`server.cfg.local`) as a **local-only** project path role (new path role or convention documented in P2-1).
- Environment profiles remain Atlas metadata; **dev/prod divergence lives in the gitignored overlay**, not in duplicate committed cfg trees.

---

## Open validation (conditional)

During P2-1, confirm on the project's pinned artifact channel:

- Trailing `exec server.cfg.local` overrides `sv_licenseKey` and `set mysql_connection_string` as expected.
- Relocated `endpoint_add_*` (only in overlay) binds the intended dev port without duplicate listeners.
- `onesync` behavior if dev-transform touches it.

If trailing `exec` override fails for a specific convar on a pinned build, fall back to **startup `+set` injection** via Atlas process supervisor (M7) for that convar only — still keeping secrets out of tracked files.

---

## References

- [Server Commands — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/server-commands/)
- [Setting up a Vanilla FXServer — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/setting-up-a-server-vanilla/)
- [Convars — Cfx.re Docs](https://docs.fivem.net/docs/scripting-reference/convars/)
- [Proxy Setup — Cfx.re Docs](https://docs.fivem.net/docs/server-manual/proxy-setup/)
- ADR-0009, ADR-0010, `docs/standards/configuration-strategy.md`
