# ONyX Claude Visual Prompt

## Purpose

This document is the strict visual/UI prompt for editing the first ONyX admin web panel.

Use it when working on:

- [apps/web-admin/dist/index.html](q:\ONyX_export\apps\web-admin\dist\index.html)

This is the single source of truth for the current web-admin UI.

Do not switch to another file unless explicitly instructed.

## Scope

Your task is to improve the visual design and layout quality of the ONyX admin panel.

This pass is:

- visual
- structural
- UX-oriented

This pass is not:

- backend redesign
- API redesign
- auth redesign
- endpoint rewiring

## Hard Constraints

You must preserve all working backend integration.

Do not break:

- cookie auth
- websocket usage
- REST fetch calls
- same-origin assumptions
- modal CRUD flows
- topology canvas
- page routing between sections

### Do not remove or rename

Do not remove or rename existing:

- `id` attributes
- JS function hooks referenced from HTML
- containers already used by script
- current top-level pages
- modal shell
- detail panel shell

In particular, preserve these structural anchors:

- `#loginWrap`
- `#appWrap`
- `#elog`
- `#alog`
- `#tc`
- `#dp`
- `#dpt`
- `#dpb`
- `#modal`
- `#modalTitle`
- `#modalBody`
- `#modalActions`
- `#btnAddNode`
- `#btnAddLink`
- `#btnAddRoutePolicy`
- `#btnAddDNSPolicy`
- `#btnAddGeoPolicy`
- `#btnAddBalancer`
- `#btnPlanPath`
- `#nodeSearch`
- `#nodeStatusFilter`
- `#linkSearch`
- `#linkStateFilter`
- `#topoSummary`
- `#topoPathSummary`

If you need different structure for styling, wrap existing elements.

Do not delete the existing hook elements.

## Backend Facts You Must Assume

The backend and runtime wiring already exist and are functional.

Available and already connected:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/nodes`
- `GET /api/v1/links`
- `GET /api/v1/route-policies`
- `GET /api/v1/dns-policies`
- `GET /api/v1/geo-policies`
- `GET /api/v1/balancers`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{id}/events`
- `GET /api/v1/audit-logs`
- `GET /api/v1/graph`
- `POST /api/v1/paths/plan`
- `WS /api/v1/ws/admin/events`

Do not replace these integrations with mock data.

## Information Architecture

The top-level navigation must remain exactly:

1. `System`
2. `Nodes`
3. `Links`
4. `Policies`
5. `Jobs`
6. `Audit / Access`
7. `Topology`
8. `API Debug`

Do not invent a different IA in this pass.

## Visual Direction

The user wants:

- dark UI
- strong operator feel
- not generic SaaS
- not toy-like
- not pastel
- not purple-biased
- not rounded-soft consumer dashboard design

Preferred direction:

- terminal-inspired precision
- cyber-infrastructure tone
- compact but readable spacing
- high-contrast typography
- strong section hierarchy
- deliberate use of accent color

This should feel like:

- control plane
- network operations console
- transport orchestration panel

Not like:

- CRM
- startup analytics template
- generic admin bootstrap clone

## Priority Areas

Focus first on:

1. `Topbar`
2. `Sidebar`
3. `Page headers`
4. `Tables`
5. `Detail panel`
6. `Modal forms`
7. `Topology page`
8. `Login screen`

### Topology page

The topology page is now real and functional.

It already has:

- live graph data
- path planning
- node/link detail interaction
- graph summary
- path overlay summary

Your task is to make it look intentional and legible.

You may improve:

- graph frame
- legend layout
- summary cards
- action bar
- spatial balance around canvas

Do not replace the canvas with a different rendering library in this pass.

## Login Screen Requirements

Keep:

- username
- password
- submit
- inline error state

Allowed:

- stronger typography
- tighter spacing
- more distinctive visual identity
- a better shell/background treatment

Do not add:

- signup
- forgot password
- OAuth
- MFA
- marketing copy

## What You May Change

You may change:

- HTML layout
- CSS variables
- spacing
- typography
- panels
- cards
- headers
- button styling
- table styling
- empty states
- visual grouping
- icon treatment
- section framing

You may add:

- wrappers
- helper classes
- non-breaking decorative elements
- layout containers

## What You Must Not Change

Do not:

- remove existing JS behavior
- convert the app into a framework
- split files
- move logic into a build system
- add external dependencies
- add CDN libraries
- change endpoint URLs
- change auth semantics
- change websocket semantics
- change same-origin assumptions

Do not break standalone serving of:

- `apps/web-admin/dist/index.html`

## Output Expectation

Return edits only for:

- [apps/web-admin/dist/index.html](q:\ONyX_export\apps\web-admin\dist\index.html)

Keep the app self-contained in that file.

## Suggested Working Method

1. Preserve all existing script hooks.
2. Improve shell layout and visual hierarchy.
3. Refine pages one by one without touching backend behavior.
4. Keep the final result readable on desktop first.
5. Prefer decisive visual choices over timid generic admin styling.

## Final Reminder

This is not a prototype anymore.

The page is already wired to a real ONyX backend.

Treat it as a live operator console with a weak visual layer that needs design improvement, not as a mock needing fake data or fake auth.
