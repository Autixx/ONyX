# ONX Claude VPN Client Prompt

## Purpose

This prompt is for Claude to work on the ONX end-user VPN desktop client.

Claude must improve and extend the client UI and client-side UX without inventing a new backend contract.

The backend contract, security model, and hidden-transport rules are already defined by ONX and must be respected.

## Canonical Files

Claude must treat these files as the current source of truth:

- `apps/client-desktop/onyx_client.py`
- `apps/client-desktop/README.md`
- `docs/architecture/ONX_CLIENT_MVP_DESIGN.md`
- `docs/architecture/ONX_CLIENT_BACKEND_CONTRACT_BLUEPRINT.md`
- `docs/architecture/ONX_CLIENT_DELIVERY_ARCHITECTURE.md`
- `docs/architecture/ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md`

If Claude updates the client implementation, the main target file is:

- `apps/client-desktop/onyx_client.py`

Do not redesign backend routes. Do not rewrite backend semantics from scratch.

## Current Backend Reality

The client backend surface already exists and must be reused.

### Available Client Endpoints

Auth:

- `POST /api/v1/client/auth/login`
- `POST /api/v1/client/auth/logout`
- `GET /api/v1/client/auth/me`

Registrations:

- `POST /api/v1/client/registrations`

Devices:

- `POST /api/v1/client/devices/register`
- `POST /api/v1/client/devices/challenge`
- `POST /api/v1/client/devices/verify`
- `GET /api/v1/client/devices/me`
- `POST /api/v1/client/devices/{id}/revoke`

Bundles:

- `POST /api/v1/client/bundles/issue`
- `GET /api/v1/client/bundles/current?device_id=...`

### Current Desktop Skeleton Already Does

- login
- registration submit
- local session persistence
- local X25519 device key generation
- device registration
- challenge request / verification
- bundle request and local decrypt
- basic dashboard rendering

### What Does Not Exist Yet

These are not implemented as production runtime behavior yet:

- real VPN tunnel connect/disconnect runtime
- real host-level DNS override
- real protocol benchmarking and transport race
- background reconnect daemon
- production-grade secure local secret vault
- final support-ticket client flow

Claude must not pretend these missing parts already exist.

## Product Direction

The ONX client must look and feel like a normal consumer VPN application.

The user should see only:

1. Login window with navigation to registration
2. Registration window
3. Main client window with:
   - connection status: enabled / disabled
   - connected / disconnected state
   - used traffic
   - live ingress / egress throughput
   - configuration expiration date
   - support entry point

The user should not be shown in the normal UX:

- the virtual tunnel interface
- split-tunnel or multihop internals
- ingress / relay / egress topology
- plaintext configs
- protocol name in use
- endpoint inventory
- DNS enforcement internals

The client should behave like a polished VPN app, not like a network engineering console.

## Required UX Rules

### 1. Login

The login screen must contain:

- username or email
- password
- login action
- switch to registration

The client may remember local session state so the app can open while offline and show cached account state.

Do not implement browser cookie logic. This is a desktop app, not a web page.

### 2. Registration

The registration screen must contain:

- username
- password
- password confirmation
- first name
- last name
- email
- referral code
- planned device count (`1..3`)
- usage goal:
  - `internet`
  - `gaming`
  - `development`

Local validation is required before submit.

### 3. Main Window

The main window must show:

- connection toggle area
- connection state
- used traffic
- ingress speed
- egress speed
- subscription/config expiration
- current user identity
- support action

It must not expose transport internals in standard mode.

### 4. Support

The client should include a visible support entry point.

If backend support endpoints are not implemented yet, the UI may present a placeholder support form or disabled state, but it must not fake a real submit flow.

### 5. Offline Behavior

If the user has logged in before, the app may open while offline and show cached state:

- username
- last known subscription/expiration
- last known traffic usage
- last known connection state

But it must not fake successful online refresh or new bundle issuance while offline.

## Visual Direction

The client should feel like a premium consumer VPN desktop app:

- restrained, modern, dark-first
- not overly technical
- not enterprise-table heavy
- not a clone of generic admin dashboards

Preferred qualities:

- clear state hierarchy
- large connect control
- strong readability
- compact but elegant telemetry presentation
- obvious primary actions
- minimal cognitive noise

Avoid:

- exposing implementation details
- raw JSON or debug text in the main UX
- admin-panel aesthetics
- giant tables as the primary layout

Diagnostics can exist, but only as a secondary panel or advanced mode.

## Technical Constraints

Claude must respect these constraints:

1. Do not change backend endpoints unless explicitly asked.
2. Do not invent new auth/token models.
3. Do not require plaintext config files.
4. Do not expose active protocol or network topology in the normal UX.
5. Do not turn the client into an operator console.
6. Do not silently remove current client bootstrap flows:
   - login
   - registration
   - device registration
   - challenge/verify
   - bundle issue/decrypt
7. Keep code grounded in the current Python desktop client unless explicitly asked to migrate frameworks.

## Framework Guidance

Current client implementation is Python + Tkinter in a single file:

- `apps/client-desktop/onyx_client.py`

Claude may improve structure and UX, but should not casually migrate the client to a different framework unless explicitly requested.

If Claude believes a future migration is justified, it may note that separately, but the primary deliverable must remain usable inside the current stack.

## What Claude Should Build First

The next useful client pass should focus on UI/UX shell, not transport runtime.

Priority order:

1. Redesign login and registration flow
2. Redesign dashboard/main client window
3. Add clear connect/disconnect state shell in the UI
4. Add traffic / speed / expiration cards
5. Add support entry point
6. Keep hidden-network rules intact
7. Preserve current backend integration points

Do not start by implementing real tunnel drivers.

## What Claude Must Not Do

Claude must not:

- redesign the ONX backend contract
- invent separate-origin web flows
- expose admin API concepts to the end user
- ask the user to paste bearer tokens manually
- expose node IPs, route graphs, or protocol internals
- replace encrypted bundle delivery with plaintext configs
- present mock-success states for unimplemented backend/runtime features

## Expected Deliverable

Claude should produce a better desktop client UI and interaction shell around the existing client bootstrap flow.

That means:

- better layout
- better styling
- better screen organization
- better state presentation
- clearer error handling
- preserved backend wiring

The output should be implementation-oriented, not just a design essay.

## Short Prompt Version

Use this if a short direct prompt is needed:

`Work only on apps/client-desktop/onyx_client.py. Read docs/architecture/ONX_CLIENT_MVP_DESIGN.md, docs/architecture/ONX_CLIENT_BACKEND_CONTRACT_BLUEPRINT.md, and docs/architecture/ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md first. Improve the ONX desktop VPN client UI/UX as a consumer VPN application, not an admin console. Preserve the existing backend contract and current client bootstrap flows: registration, login, device registration, challenge/verify, and encrypted bundle issuance/decrypt. Do not invent new backend routes, do not require plaintext configs, do not expose protocol/topology/internal DNS behavior in the normal UX, and do not replace the current Python desktop stack unless explicitly asked. Focus on login, registration, dashboard, connect/disconnect shell, traffic/speed/expiration display, support entry point, offline cached-state behavior, and clear error handling.`
