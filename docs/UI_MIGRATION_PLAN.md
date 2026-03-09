# UI Migration Plan

Last updated: 2026-03-09
Status: In progress

## Goal

Replace the monolithic `apps/ui/index.html` with a modular, route-based legal workbench built with React + Vite.

Current implementation status:
- Vite + React shell is active in `apps/ui`
- legacy monolith has been moved to `apps/ui/legacy-index.html`
- route shell, shared layout, matter list, matter detail tabs, documents, search, tasks, drafts, settings, assistant, connectors and onboarding surfaces now exist as modular React pages
- further work should extend the modular shell, not the legacy file

## Current State

Current UI characteristics:
- single HTML file
- inline styles and scripts
- many product surfaces mixed together
- strong prototype coverage, weak maintainability

## Target Structure

```text
apps/ui/
  index.html
  legacy-index.html
  src/
    app/
      AppShell.tsx
      Router.tsx
      AppContext.tsx
    pages/
      DashboardPage.tsx
      MattersPage.tsx
      MatterDetailPage.tsx
      DocumentsPage.tsx
      AssistantPage.tsx
      TasksPage.tsx
      DraftsPage.tsx
      SettingsPage.tsx
      ConnectorsPage.tsx
      OnboardingPage.tsx
    components/
      layout/
      common/
      matters/
      documents/
      citations/
      tasks/
      drafts/
      activity/
      settings/
    services/
      apiClient.ts
      lawcopilotApi.ts
    styles/
      tokens.css
      globals.css
    test/
      setupTests.ts
      test-utils.tsx
```

## Route Map

- `/dashboard`
- `/matters`
- `/matters/:matterId`
- `/documents`
- `/assistant`
- `/tasks`
- `/drafts`
- `/settings`
- `/connectors`
- `/onboarding`

## Prototype-to-Module Mapping

| Current surface in `index.html` | Target module |
| --- | --- |
| Dashboard | `DashboardPage` |
| Documents and search area | `DocumentsPage` |
| Assistant chat/output area | `AssistantPage` |
| Tasks / kanban / due-date surfaces | `TasksPage` plus matter-local task panels |
| Settings / model controls | `SettingsPage` |
| Connectors | `ConnectorsPage` |
| Onboarding wizard | `OnboardingPage` |
| Notification/history panels | `ActivityDrawer` and `NotificationsPanel` |
| Document preview and compare areas | `DocumentViewer`, `SearchResultsPanel`, `ComparePanel` |

## UX Rules to Preserve

- Matter context must always remain visible.
- AI outputs must distinguish:
  - document-backed
  - inferred
  - draft
  - manual-review-required
- Citations must be visually richer than generic search rows.
- The workbench should feel like a case workspace, not a consumer chat tool.

## Migration Slices

### Slice 1
- bootstrap Vite + React app
- create AppShell and routing
- migrate shared tokens and layout

Status: Completed

### Slice 2
- move Dashboard and Matters list
- add persistent matter context shell

Status: Completed

### Slice 3
- move Matter detail with tabs:
  - summary
  - documents
  - search
  - tasks
  - drafts
  - timeline

Status: Completed

### Slice 4
- refine search workbench and document viewer
- add citation jump and chunk preview

Status: In progress

### Slice 5
- move Assistant, Drafts, Settings, Connectors
- relegate legacy UI to temporary compatibility wrapper

Status: Partially completed

## Current route surface

- `/dashboard`
- `/matters`
- `/matters/:matterId`
- `/documents`
- `/assistant`
- `/tasks`
- `/drafts`
- `/settings`
- `/connectors`
- `/onboarding`

Matter detail tabs currently implemented:
- `summary`
- `documents`
- `search`
- `tasks`
- `drafts`
- `timeline`

## Legacy Strategy

- Keep legacy UI as `legacy-index.html` during migration.
- `index.html` is now the Vite entrypoint for the modular shell.
- Once core flows are migrated, legacy UI can be deleted or turned into a static archive artifact.
- Do not add meaningful new product behavior directly into the old monolith after the new shell exists.

## Acceptance Criteria

- Core user flows run in modular React pages.
- Shared primitives replace one-off inline UI blocks.
- New UI has a testable component tree.
