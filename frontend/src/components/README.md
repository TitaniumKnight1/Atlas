# frontend\src\components

## Responsibility

Shared presentational components reused across features.

## Belongs here

- Design-system primitives: buttons, form controls, toggles, tabs, badges, chips, surfaces, tables, dialogs, feedback, tooltips, and sparklines
- Shared state and command primitives used by feature slices
- Small hooks that adapt presentation to existing API/SSE clients

## Does not belong here

- Feature-specific workflows
- Direct API orchestration for complex use cases
- Hardcoded color values; components consume `frontend/src/styles.css` tokens

## See also

[docs/architecture/frontend.md](../docs/architecture/frontend.md)
