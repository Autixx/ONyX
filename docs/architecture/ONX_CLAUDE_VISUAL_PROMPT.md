# ONyX Claude Visual Prompt

## Purpose

This document is the strict visual/UI prompt for editing the current ONyX admin web panel.

Use it when working on:

- [apps/web-admin/dist/index.html](q:\ONyX_export\apps\web-admin\dist\index.html)

This file is the single source of truth for the admin web UI.

Do not switch to another file unless explicitly instructed.

## Current Project State

The project is not backend-only anymore.

Current state:

- backend routes are real
- browser auth is real
- websocket event stream is real
- same-origin static hosting is real
- admin web UI is already wired
- desktop client skeleton also exists, but it is not the target of this prompt

This means:

- do not redesign API behavior
- do not replace working logic with mock data
- do not invent new frontend/backend contracts

Your job is visual and structural refinement of the existing admin UI only.

## Scope

This pass is:

- visual
- layout-oriented
- UX-oriented
- same-file

This pass is not:

- backend redesign
- endpoint redesign
- auth redesign
- build-system migration
- framework conversion

## Hard Constraints

You must preserve all working backend integration.

Do not break:

- cookie admin auth
- websocket usage
- REST fetch calls
- same-origin assumptions
- modal CRUD flows
- detail panel flows
- topology SVG interaction
- page routing between sections

### Do not remove or rename

Do not remove or rename existing:

- `id` attributes already used by script
- JS hooks referenced from HTML
- current page containers
- modal shell
- detail panel shell

In particular, preserve these anchors:

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
- `#btnAddUser`
- `#btnAddPlan`
- `#btnAddSubscription`
- `#btnAddReferralCode`
- `#btnPlanPath`
- `#nodeSearch`
- `#nodeStatusFilter`
- `#trafficSearch`
- `#trafficStateFilter`
- `#linkSearch`
- `#linkStateFilter`
- `#topoSummary`
- `#topoPathSummary`

If you need a different layout for styling, wrap or regroup existing elements.

Do not delete the existing hook elements.

## Backend Facts You Must Assume

The backend and current UI wiring already exist and are functional.

### Browser auth

Already real:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

### Admin/control-plane data already wired in the current UI

- `GET /api/v1/health`
- `GET /api/v1/health/worker`
- `GET /api/v1/nodes`
- `GET /api/v1/node-traffic/summary`
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
- `GET /api/v1/registrations`
- `GET /api/v1/peers`
- `GET /api/v1/users`
- `GET /api/v1/plans`
- `GET /api/v1/subscriptions`
- `GET /api/v1/referral-codes`
- `GET /api/v1/devices`
- `WS /api/v1/ws/admin/events`

### Existing admin actions already wired

- node create / edit / delete
- node discover
- node bootstrap-runtime
- node traffic reset / rollover
- link create / edit / delete / validate / apply
- route policy create / edit / delete / apply
- DNS policy create / edit / delete / apply
- geo policy create / edit / delete / apply
- balancer create / edit / delete / pick
- jobs cancel / retry / force-cancel
- registrations approve / reject
- user create / edit / delete
- plan create / edit / delete
- subscription create / edit / delete
- referral code create / edit / delete
- device revoke

Do not replace any of these integrations with fake data.

## Information Architecture

The top-level navigation must remain aligned with the current real admin UI.

Current top-level sections are:

1. `System`
2. `Nodes`
3. `Node Traffic`
4. `Links`
5. `Peers`
6. `Policies`
7. `Jobs`
8. `Registrations`
9. `Audit / Access`
10. `Topology`
11. `API Debug`

Do not invent a different top-level IA in this pass.

You may visually regroup or refine them, but the section structure must remain intact.

## Visual Direction

The user wants:

- dark UI
- operator feel
- strong infrastructure/control-plane tone
- not generic SaaS
- not toy-like
- not consumer-dashboard aesthetics
- not pastel
- not purple-biased
- not soft rounded startup admin styling

Preferred direction:

- terminal-inspired precision
- cyber-infrastructure tone
- compact but readable spacing
- strong typography hierarchy
- sharper panels and table rhythm
- disciplined accent usage

This should feel like:

- network operations console
- transport orchestration panel
- control plane

Not like:

- startup analytics template
- CRM
- bootstrap dashboard clone

## Priority Areas

Focus first on:

1. `Topbar`
2. `Navigation tabs`
3. `Login screen`
4. `Tables`
5. `System page stat cards`
6. `Node / Link / Policy data density`
7. `Detail panel`
8. `Modal forms`
9. `Topology`
10. `Registrations / Identity page`

## Topology Page

The topology page is functional.

It already has:

- real graph data
- path planning
- node detail interaction
- link detail interaction
- graph summary
- path overlay summary

Your task is to make it look intentional and legible.

You may improve:

- graph frame
- legend
- summary cards
- action bar
- spacing and composition around the SVG

Do not replace SVG rendering with another rendering library in this pass.

## Registrations / Identity Page

This page is no longer only about pending registrations.

It now contains:

- registrations
- users
- subscriptions
- plans
- referral codes
- devices

Treat it as an identity/access management screen inside the admin panel.

It should remain readable and not collapse into visual noise.

## Login Screen Requirements

Keep:

- username
- password
- submit
- inline error state

Allowed:

- stronger typography
- sharper form shell
- more distinctive visual identity
- better background treatment

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
- table styling
- button styling
- empty states
- section framing
- layout grouping
- visual separators
- wrappers and helper classes

You may add:

- non-breaking layout wrappers
- helper containers
- decorative elements that do not interfere with existing JS hooks

## What You Must Not Change

Do not:

- remove existing JS behavior
- convert the page into React/Vue/Svelte/etc.
- split files
- introduce a build step
- add CDN libraries
- add external dependencies
- change endpoint URLs
- change auth semantics
- change websocket semantics
- change same-origin assumptions
- replace modal CRUD flows with unfinished placeholders

Do not break standalone serving of:

- [apps/web-admin/dist/index.html](q:\ONyX_export\apps\web-admin\dist\index.html)

## Output Expectation

Return edits only for:

- [apps/web-admin/dist/index.html](q:\ONyX_export\apps\web-admin\dist\index.html)

Keep the app self-contained in that single file.

## Suggested Working Method

1. Preserve all existing script hooks.
2. Improve shell layout and visual hierarchy first.
3. Improve table readability and action density second.
4. Improve modal/detail panel consistency third.
5. Improve topology composition last.
6. Keep desktop-first readability.

## Final Reminder

This is not a mock.

The page is already wired to a real ONyX backend and real admin actions.

Treat it as a live operator console whose weak point is visual quality, not backend completeness.
