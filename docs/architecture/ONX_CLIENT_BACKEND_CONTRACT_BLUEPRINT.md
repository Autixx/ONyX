# ONX Client Backend Contract Blueprint

## Status

Draft v0.1

## Purpose

This document converts the client MVP design into an implementation-oriented backend blueprint.

It defines:

- which backend modules are required
- which database entities are required
- which API contours are required
- which contracts must be stabilized before desktop client runtime work starts
- what can be reused from the current ONX alpha

This is the backend implementation contract for the future client.

It is not end-user documentation and not a UI brief.

## Scope

This blueprint covers only the client-facing backend layer and the minimum admin-side data model needed to support it.

It does not define:

- the full desktop app implementation
- frontend admin UI details
- payment provider adapters
- mobile-specific runtime behavior

## Current ONX Reuse Baseline

The following pieces already exist and should be reused instead of redesigned:

### 1. Existing Control-Plane Runtime

- `nodes`
- `links`
- `route policies`
- `dns policies`
- `geo policies`
- `balancers`
- `topology graph`
- `path planner`
- job system
- audit logs
- realtime websocket event bus

### 2. Existing Client-Routing Control Protocol

Already present:

- `POST /api/v1/bootstrap`
- `POST /api/v1/probe`
- `POST /api/v1/best-ingress`
- `POST /api/v1/session-rebind`

This protocol remains useful, but it is not enough by itself for the full user client.

### 3. Existing Browser/Admin Auth

Already present:

- admin web auth
- admin session cookies
- admin API ACL

This must not be reused as the end-user client auth model.

### 4. Existing Registration / Peer Stubs

The repo already contains initial backend modules for:

- `registrations`
- `peers`

These should be treated as early admin-oriented or placeholder modules and hardened against the final client contract, not discarded blindly.

## Core Rule

The end-user client must receive runtime connectivity from a dedicated client delivery API contour, not from the admin panel UI.

That means:

- admin UI is operator-only
- client app uses separate auth/session/device/bundle endpoints
- the same ONX backend deployment may serve both surfaces
- but the contracts must remain logically separated

## Target Backend Workstreams

Implementation should be split into five backend workstreams.

### Workstream A: Identity

Goal:

- represent users and their access status

Deliverables:

- `users`
- user auth endpoints
- registration request flow

### Workstream B: Entitlement

Goal:

- represent service rights independently of transports

Deliverables:

- `plans`
- `subscriptions`
- entitlement evaluation

### Workstream C: Device Binding

Goal:

- bind access to registered devices

Deliverables:

- `devices`
- device metadata
- device key registration
- challenge-response verification

### Workstream D: Bundle Delivery

Goal:

- issue encrypted runtime bundle to valid user+device

Deliverables:

- bundle envelope definition
- bundle issuance endpoint
- bundle refresh/rebind endpoint
- issuance audit trail

### Workstream E: Client Support Surface

Goal:

- let the application report support incidents and operational metadata

Deliverables:

- support ticket endpoint
- ticket persistence
- ticket audit trail

## Required Data Model

## 1. Users

Table: `users`

Minimum fields:

- `id`
- `username`
- `email`
- `password_hash`
- `status`
- `first_name`
- `last_name`
- `referral_code`
- `usage_goal`
- `requested_device_count`
- `created_at`
- `updated_at`

Recommended status values:

- `pending`
- `active`
- `blocked`
- `deleted`

Notes:

- `usage_goal` should map to client-side protocol preference
- `requested_device_count` is input to operator or policy decision, not the final enforcement field

## 2. Registration Requests

Table: `registration_requests`

Purpose:

- capture sign-up before activation

Minimum fields:

- `id`
- `username`
- `email`
- `password_hash`
- `first_name`
- `last_name`
- `referral_code`
- `usage_goal`
- `requested_device_count`
- `status`
- `reviewed_by`
- `reviewed_at`
- `reject_reason`
- `created_at`
- `updated_at`

Recommended status values:

- `pending`
- `approved`
- `rejected`

Note:

This can supersede or evolve the current `registrations` placeholder module.

## 3. Plans

Table: `plans`

Minimum fields:

- `id`
- `code`
- `name`
- `enabled`
- `billing_mode`
- `default_device_limit`
- `default_usage_goal_policy`
- `traffic_quota_bytes` nullable
- `created_at`
- `updated_at`

## 4. Subscriptions

Table: `subscriptions`

Minimum fields:

- `id`
- `user_id`
- `plan_id`
- `status`
- `billing_mode`
- `starts_at`
- `expires_at`
- `device_limit`
- `suspended_at`
- `revoked_at`
- `created_at`
- `updated_at`

Recommended status values:

- `pending`
- `active`
- `grace`
- `suspended`
- `expired`
- `revoked`

## 5. Devices

Table: `devices`

Minimum fields:

- `id`
- `user_id`
- `subscription_id`
- `device_public_key`
- `device_label`
- `platform`
- `status`
- `first_registered_at`
- `last_seen_at`
- `last_ip`
- `last_asn`
- `revoked_at`
- `created_at`
- `updated_at`

Recommended status values:

- `pending`
- `active`
- `revoked`
- `blocked`

## 6. Device Metadata / Attestation

Table: `device_metadata`

Purpose:

- store non-secret descriptive context and risk signals

Minimum fields:

- `device_id`
- `app_version`
- `os_name`
- `os_version`
- `device_model`
- `app_instance_id`
- `attestation_type`
- `attestation_summary`
- `last_ip`
- `last_asn`
- `updated_at`

## 7. Client Sessions

Either extend existing `client_sessions` or add a dedicated user-facing session table.

Required semantics:

- authenticated user session
- linked device where available
- server session expiry
- last activity time

Minimum fields:

- `id`
- `user_id`
- `device_id` nullable
- `session_token_hash`
- `status`
- `created_at`
- `expires_at`
- `last_seen_at`

## 8. Bundle Events / Issued Bundles

Table: `issued_bundles` or `bundle_events`

Purpose:

- audit runtime delivery
- allow safe re-issue/rebind tracking

Minimum fields:

- `id`
- `user_id`
- `device_id`
- `session_id`
- `bundle_version`
- `bundle_hash`
- `issued_at`
- `expires_at`
- `revoked_at`
- `reason`
- `selected_transport`
- `selected_ingress_node_id`

## 9. Support Tickets

Table: `support_tickets`

Minimum fields:

- `id`
- `user_id`
- `device_id`
- `session_id` nullable
- `issue_type`
- `message`
- `client_version`
- `os_name`
- `os_version`
- `connection_state`
- `status`
- `created_at`
- `updated_at`

Recommended statuses:

- `open`
- `triaged`
- `resolved`
- `closed`

## Required Services

The backend should gain the following services.

## 1. `user_service`

Responsibilities:

- create user from approved registration
- load user by id / username / email
- block / unblock user
- validate basic user state

## 2. `registration_service`

Responsibilities:

- create registration request
- validate registration payload
- approve / reject request
- transform approved request into active user record

## 3. `plan_service`

Responsibilities:

- CRUD for plans
- read effective defaults

## 4. `subscription_service`

Responsibilities:

- assign subscription
- check expiration
- set lifetime
- suspend / unsuspend / revoke
- return effective device limit

## 5. `device_service`

Responsibilities:

- register device key
- track active devices
- enforce device limit
- revoke / replace device
- store device metadata

## 6. `entitlement_service`

Responsibilities:

- produce normalized access decision
- decide whether bundle issuance is allowed
- expose clear denial reason

Expected output shape:

- `is_allowed`
- `reason`
- `subscription_id`
- `plan_code`
- `device_limit`
- `active_device_count`
- `usage_goal`
- `traffic_quota_bytes`

## 7. `device_challenge_service`

Responsibilities:

- create nonce/challenge
- verify device signature
- validate challenge freshness

## 8. `bundle_service`

Responsibilities:

- select ingress candidates
- select transport candidates
- assemble encrypted bundle envelope
- issue bundle
- renew bundle
- revoke or invalidate stale bundle state

## 9. `support_service`

Responsibilities:

- create support ticket
- normalize client diagnostics payload
- allow admin read/review later

## Required Client API Groups

The final client-facing surface should be grouped like this.

## 1. Authentication

Recommended endpoints:

- `POST /api/v1/client/auth/login`
- `POST /api/v1/client/auth/logout`
- `GET /api/v1/client/auth/me`
- `POST /api/v1/client/auth/refresh` later if needed

Notes:

- do not reuse admin web auth routes for the client application
- keep auth namespace explicit

## 2. Registration

Recommended endpoints:

- `POST /api/v1/client/registrations`
- `GET /api/v1/client/registrations/{id}` optional

Admin side:

- approval and rejection may stay under admin routes

## 3. Devices

Recommended endpoints:

- `POST /api/v1/client/devices/register`
- `POST /api/v1/client/devices/challenge`
- `POST /api/v1/client/devices/verify`
- `GET /api/v1/client/devices/me`
- `POST /api/v1/client/devices/{id}/revoke` later

## 4. Bundles

Recommended endpoints:

- `POST /api/v1/client/bundles/issue`
- `POST /api/v1/client/bundles/rebind`
- `GET /api/v1/client/bundles/current`

## 5. Support

Recommended endpoints:

- `POST /api/v1/client/support/tickets`
- `GET /api/v1/client/support/tickets/{id}` optional later

## 6. Existing Routing Endpoints

Current endpoints:

- `POST /api/v1/bootstrap`
- `POST /api/v1/probe`
- `POST /api/v1/best-ingress`
- `POST /api/v1/session-rebind`

Recommendation:

- keep them as lower-level control protocol
- do not expose them as the full user auth/session surface
- let `bundle_service` and client runtime call into this logic internally or via adapted contract

## Contract Stability Rules

Before desktop runtime implementation begins, the following contracts must be frozen enough to avoid rework:

### Must Stabilize First

- registration payload
- user auth response shape
- device registration payload
- challenge-response payload
- bundle envelope shape
- entitlement denial reasons

### Can Remain Internal Longer

- exact admin CRUD for users/plans/subscriptions
- internal bundle encryption implementation details
- support ticket operator workflow

## Recommended Response Contracts

## 1. Registration Create Response

Must at minimum return:

- `registration_id`
- `status`
- `message`

## 2. Client Login Response

Must return:

- `user_id`
- `username`
- `status`
- `session_expires_at`
- `subscription_summary`

## 3. Device Register Response

Must return:

- `device_id`
- `status`
- `challenge_required`
- `device_limit`
- `active_device_count`

## 4. Device Verify Response

Must return:

- `device_id`
- `verified`
- `entitlement_allowed`
- `entitlement_reason`

## 5. Bundle Issue Response

Must return:

- `bundle_id`
- `device_id`
- `issued_at`
- `expires_at`
- `encrypted_bundle`
- `bundle_format_version`

Optional:

- `transport_summary`
- `selected_goal_policy`

## Why Bundle Must Stay Separate From Raw Config

The backend contract must not devolve into:

- “download .conf”

because that breaks:

- device binding
- protocol agility
- fallback selection
- hidden topology requirement

The backend must issue:

- encrypted runtime projection

not:

- reusable user-facing config artifact

## Suggested Phased Backend Implementation

## Phase 1: Identity Core

Implement:

- `users`
- `registration_requests`
- `plans`
- `subscriptions`

Exit condition:

- registration can create approved user
- user can log in
- subscription state exists

## Phase 2: Device Binding

Implement:

- `devices`
- `device_metadata`
- device register
- challenge-response
- device limit evaluation

Exit condition:

- one user can bind one device safely

## Phase 3: Bundle Delivery

Implement:

- `issued_bundles`
- bundle issue endpoint
- encrypted envelope
- rebind endpoint
- entitlement gating

Exit condition:

- backend can issue device-bound bundle

## Phase 4: Support and Operational Fit

Implement:

- support ticket endpoint
- better denial diagnostics
- device revocation / replacement flow

Exit condition:

- client MVP can operate without hidden manual backend interventions

## Constraints and Safety Rules

### 1. Do Not Mix Admin and Client Auth

Do not reuse:

- admin web session
- admin token model

for the desktop client.

### 2. Do Not Put Full Topology Into Client Contract

The client must receive only:

- ingress candidates
- transport candidates
- DNS target
- expiry
- opaque control tokens

### 3. Do Not Start With Payment Automation

Payment adapters are later.

Manual subscription control is enough for the first client-compatible backend slice.

### 4. Do Not Start With All Protocols

The backend contract should be protocol-agnostic, but the first working runtime path can still be:

- AWG first
- WG/OpenVPN next
- Xray later

## Proposed Immediate Next Step

The next concrete implementation slice should be:

1. `users`
2. `registration_requests`
3. `plans`
4. `subscriptions`
5. `client auth endpoints`

Only after that should device registration and bundle issuance begin.
