# ONyX Claude UI Prompt Spec

## Purpose

This document is the strict frontend handoff prompt for building the first ONyX web UI.

It is intentionally narrower than the full web handoff.

Use this document as the primary implementation brief for the first UI pass.

## Project Scope

Build the first ONyX admin web UI on top of the existing ONyX backend.

This is an operator/admin UI only.

Do not build a public client cabinet.

Do not redesign backend contracts unless explicitly requested.

## Backend Facts You Must Assume

The backend foundation already exists.

Available backend capabilities:

- same-origin deployment model
- HTTPS through nginx reverse proxy
- browser login/session auth
- secure HTTP-only session cookie
- websocket admin event stream
- REST admin API
- static UI hosting scaffold
- job/event/audit model
- ACL-controlled admin API

Relevant backend endpoints:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/health`
- `GET /api/v1/health/worker`
- `WS /api/v1/ws/admin/events`

The backend mounts UI from:

- `/opt/onyx/apps/web-admin/dist`

If that build directory exists, ONyX serves the UI from `/`.

The API stays under:

- `/api/v1/...`

## Authentication Requirements

### Required behavior

Implement a login screen using:

- username
- password

Submit credentials to:

- `POST /api/v1/auth/login`

The backend sets the session cookie.

The UI must not store auth tokens manually.

The browser may save the username/password in its password manager.

That is allowed.

### Session behavior

Required UX rule:

- session remains active while the user is actively using the panel
- session is terminated after 15 minutes of inactivity

Backend note:

- current backend session idle timeout is configurable through env
- UI should assume idle timeout is authoritative on the backend

Frontend requirement:

- if `/api/v1/auth/me` returns `401`, redirect to login
- if websocket disconnects because session expired, redirect to login

### Logout

Use:

- `POST /api/v1/auth/logout`

After logout:

- clear in-memory user state
- return to login screen

## Navigation Requirements

After authentication, the panel structure must mirror the ONX admin TUI sections.

Top-level navigation must be:

1. `System`
2. `Nodes`
3. `Links`
4. `Policies`
5. `Jobs`
6. `Audit / Access`
7. `Topology`
8. `API Debug`

Do not invent a different top-level IA for the first pass.

The UI should feel like a web version of the `onx` admin menu.

## Visual Direction

General direction:

- dark interface
- technical/operator look
- not playful
- not glossy consumer SaaS
- dense enough for operators
- readable on desktop first

The user explicitly prefers a dark UI.

### Login screen

Required:

- centered login form
- username field
- password field
- submit button
- error state

Allowed:

- browser-managed password saving

Do not add:

- sign up
- forgot password
- SSO
- MFA

## Realtime Requirements

Use websocket, not polling, for live updates where possible.

Websocket endpoint:

- `WS /api/v1/ws/admin/events`

Use it for:

- job state changes
- audit event feed
- connection status

Expected event types currently include:

- `system.connected`
- `system.ping`
- `job.created`
- `job.started`
- `job.claimed`
- `job.cancel_requested`
- `job.retry_requested`
- `job.cancelled`
- `job.step`
- `job.succeeded`
- `job.failed`
- `job.retry_scheduled`
- `audit.event`

Fallback:

- if some pages still need one-shot fetches, use normal REST
- but do not design the UI around periodic GET polling as the primary update model

## Data/Backend Rules

### Same-origin assumption

Assume:

- UI and API are served from the same origin
- no CORS work is needed

Do not build the first UI around separate frontend/backend origins.

### Static hosting assumption

Assume:

- final production build will be copied to `/opt/onyx/apps/web-admin/dist`
- backend/nginx will serve it from the same host

### ACL behavior

Backend can return:

- `401` when not authenticated
- `403` when authenticated but not authorized

UI requirements:

- `401` => go to login
- `403` => show denied state for that screen/action

Do not assume every logged-in user is full admin forever.

## What Exists Already

You may rely on:

- REST routers grouped by domain
- websocket transport
- browser auth endpoints
- nginx TLS path
- same-origin static hosting support
- backend docs in:
  - `docs/architecture/ONX_WEB_UI_HANDOFF.md`
  - `docs/architecture/ONX_TECHNICAL_DESIGN.md`

## What Does Not Exist Yet

Do not assume these exist:

- public user portal
- multi-user operator management screens
- refresh token flow
- cross-origin frontend hosting
- client subscription/billing UI
- Xray/OpenVPN/WireGuard UI modules

Those are future phases.

## What You Must Not Do

1. Do not invent a separate auth backend.
2. Do not require manual bearer-token entry.
3. Do not assume polling is the primary realtime model.
4. Do not split UI and API into different origins.
5. Do not build pages for modules that do not exist yet.
6. Do not redesign the menu tree away from the `onx` admin CLI sections.
7. Do not expose internal secrets in the UI.

## First Deliverable

The first frontend deliverable should include:

1. login page
2. authenticated app shell
3. top-level navigation matching `onx`
4. websocket connection bootstrap
5. session-aware logout behavior
6. placeholder section screens wired to existing backend groups

The first pass does not need perfect feature completeness inside every section.

It must provide the correct shell, auth model, and section structure.
