# ONX Client Delivery Architecture

## Status

Draft v0.1

## Purpose

This document defines how ONX should deliver runtime client access without exposing the full control-plane topology.

It separates:

- admin UI
- control-plane core
- client delivery API
- future delivery gateway

## Core Rule

Client access must not be issued by the admin UI as a user-facing config download.

Client access must be issued by a dedicated client-facing API surface backed by the ONX control-plane state.

The admin UI may trigger or inspect state changes, but it must not be the runtime source of truth for client bundle delivery.

## Main Components

### 1. Admin UI

Purpose:

- operator workflows
- topology management
- node/link/policy CRUD
- access rules
- subscription and device administration later

This is the operator surface only.

It must not be required by the client application.

### 2. Control-Plane Core

Purpose:

- store desired state
- store entitlement and device state
- compute ingress and path decisions
- issue encrypted session bundles

This is the real source of truth.

### 3. Client Delivery API

Purpose:

- login/session bootstrap
- device registration
- challenge-response
- bundle issuance
- session rebind

This is the application-facing runtime API.

It is logically separate from the admin API even if both live in the same backend process at first.

### 4. Optional Future Delivery Gateway

Purpose:

- expose only client-facing endpoints publicly
- scale separately from admin/control-plane traffic
- read from control-plane DB or replica

This is a later scaling layer, not a v1 requirement.

## Recommended Deployment Stages

### Stage A: Single Deployment

One backend deployment contains:

- admin API
- client API
- bundle issuance
- one PostgreSQL database

This is the correct alpha architecture.

### Stage B: Logical Split

Use separate public names:

- `admin.example.com`
- `api.example.com`

Still backed by one ONX deployment if needed.

### Stage C: Physical Split

Introduce:

- dedicated client delivery gateway
- optional read replica
- independent horizontal scaling

Only do this after the protocol and product shape are stable.

## Why Dynamic Delivery Is Better Than Static Config Storage

The runtime client profile should be generated dynamically.

Reasons:

- device binding must be checked at issue time
- subscription state must be checked at issue time
- ingress candidates should reflect current health
- path and transport choices may change over time
- short-lived bundles are safer than reusable stored configs

Therefore the primary output is:

- dynamic encrypted session bundle

Not:

- static config file copied from storage

## What the Client Needs

The client should only receive the minimum necessary runtime projection:

- a few ingress candidates
- a few transport candidates
- route token
- expiry time
- integrity/authentication data

The client should not receive:

- full node inventory
- relay graph
- internal balancer state
- operator route policy internals
- full topology history

## Bootstrap Model for App Store Distribution

For public client applications, the shipped app should contain only:

- `1-3` bootstrap domain names
- trust anchor or pinned public key
- protocol version

The app should not contain:

- static service credentials
- reusable tunnel configs
- full topology data

After install, the app should:

1. contact bootstrap API
2. authenticate user
3. register device
4. complete challenge-response
5. fetch encrypted session bundle
6. establish runtime transport

## API Separation

Recommended client-facing API groups:

- `/api/v1/auth/*`
- `/api/v1/devices/*`
- `/api/v1/bundles/*`
- `/api/v1/bootstrap`
- `/api/v1/probe`
- `/api/v1/best-ingress`
- `/api/v1/session-rebind`

Recommended admin-facing API groups:

- `/api/v1/nodes/*`
- `/api/v1/links/*`
- `/api/v1/route-policies/*`
- `/api/v1/dns-policies/*`
- `/api/v1/geo-policies/*`
- `/api/v1/balancers/*`
- `/api/v1/access-rules/*`
- `/api/v1/audit-logs`
- `/api/v1/maintenance/*`

## Security Model

The client delivery API should use:

- user auth
- device registration
- device-bound challenge-response
- rate limits
- short-lived bundles

The admin API should use:

- separate admin auth
- role-based access control
- audit logging

These two surfaces must remain logically distinct.

## Database Guidance

For the current alpha and early v0.3 work:

- one PostgreSQL database is correct

No separate bundle database or “config storage synchronizer” is required at this stage.

If scale requires it later, add:

- read replica
- cache
- delivery gateway

But keep the source of truth in the control-plane data model.

## Where Static Storage Is Still Useful

Object storage may still be useful later for:

- client update manifests
- signed release binaries
- large geo datasets
- exported backups
- non-runtime static artifacts

It should not be the primary source for live bundle issuance decisions.

## Operational Recommendation

Near-term architecture should be:

1. ONX control-plane backend
2. client delivery API in the same deployment
3. one PostgreSQL database
4. short-lived encrypted bundle issuance
5. optional future gateway only after the protocol stabilizes

## Immediate Next Step

The next implementation slice should treat the client delivery architecture as:

- one logical API contour inside ONX now
- a future separable delivery gateway later
