# ONyX Backend — Prompt for Missing Module Implementation

## Context

This prompt continues ONyX development as a control plane for overlay transport orchestration.

The frontend (`apps/web-admin/dist/index.html`) is already implemented and partially integrated with the backend. Some screens and actions rely on API modules that do not exist yet. The backend work must implement only the missing modules and fields while preserving the current ONyX architecture and working routes.

This document is synchronized with the ONyX routes that already exist in the repository.

## Strict Architectural Rules

### What is allowed

- Add new FastAPI routers under the current `onx/api/routers/` structure.
- Add new SQLAlchemy models under `onx/db/models/`.
- Add new Alembic migrations.
- Add new Pydantic schemas under `onx/schemas/`.
- Extend existing models with additive fields through migrations.
- Follow the current backend conventions already used by ONyX.

### What must not be changed without necessity

- Do not redesign the auth model under `/api/v1/auth/*`.
- Do not change the existing routes that already work.
- Do not rename existing response fields used by the frontend.
- Do not switch auth away from HTTP-only cookie sessions for the admin web UI.
- Do not introduce a second origin or separate browser auth flow.

## Routes Already Implemented in ONyX

These are real routes already present in the backend and should be treated as stable unless there is a hard reason to change them.

### Auth

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`

### Health / system

- `GET /api/v1/health`
- `GET /api/v1/health/worker`
- `GET /api/v1/maintenance/retention`
- `POST /api/v1/maintenance/cleanup`

### Nodes

- `GET /api/v1/nodes`
- `POST /api/v1/nodes`
- `GET /api/v1/nodes/{id}`
- `GET /api/v1/nodes/{id}/traffic`
- `PATCH /api/v1/nodes/{id}`
- `DELETE /api/v1/nodes/{id}`
- `PUT /api/v1/nodes/{id}/secret`
- `GET /api/v1/nodes/{id}/capabilities`
- `POST /api/v1/nodes/{id}/discover`
- `POST /api/v1/nodes/{id}/bootstrap-runtime`

### Links

- `GET /api/v1/links`
- `POST /api/v1/links`
- `GET /api/v1/links/{id}`
- `PATCH /api/v1/links/{id}`
- `DELETE /api/v1/links/{id}`
- `POST /api/v1/links/{id}/validate`
- `POST /api/v1/links/{id}/apply`

### Policies

- `GET /api/v1/route-policies`
- `POST /api/v1/route-policies`
- `GET /api/v1/route-policies/{id}`
- `GET /api/v1/route-policies/{id}/plan`
- `PATCH /api/v1/route-policies/{id}`
- `DELETE /api/v1/route-policies/{id}`
- `POST /api/v1/route-policies/{id}/apply`
- `POST /api/v1/route-policies/{id}/apply-planned`

- `GET /api/v1/dns-policies`
- `POST /api/v1/dns-policies`
- `GET /api/v1/dns-policies/{id}`
- `PATCH /api/v1/dns-policies/{id}`
- `DELETE /api/v1/dns-policies/{id}`
- `POST /api/v1/dns-policies/{id}/apply`

- `GET /api/v1/geo-policies`
- `POST /api/v1/geo-policies`
- `GET /api/v1/geo-policies/{id}`
- `PATCH /api/v1/geo-policies/{id}`
- `DELETE /api/v1/geo-policies/{id}`
- `POST /api/v1/geo-policies/{id}/apply`

### Balancers

- `GET /api/v1/balancers`
- `POST /api/v1/balancers`
- `GET /api/v1/balancers/{id}`
- `PATCH /api/v1/balancers/{id}`
- `DELETE /api/v1/balancers/{id}`
- `POST /api/v1/balancers/{id}/pick`

### Jobs / audit / access

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{id}`
- `GET /api/v1/jobs/{id}/events`
- `POST /api/v1/jobs/{id}/cancel`
- `POST /api/v1/jobs/{id}/retry-now`
- `POST /api/v1/jobs/{id}/force-cancel`

- `GET /api/v1/audit-logs`
- `GET /api/v1/access-rules`
- `GET /api/v1/access-rules/matrix`
- `PUT /api/v1/access-rules/{permission_key}`
- `DELETE /api/v1/access-rules/{permission_key}`

### Graph / planner / realtime

- `GET /api/v1/graph`
- `POST /api/v1/paths/plan`
- `WS /api/v1/ws/admin/events`

### Client routing

- `POST /api/v1/bootstrap`
- `POST /api/v1/probe`
- `POST /api/v1/best-ingress`
- `POST /api/v1/session-rebind`

### Peer traffic telemetry

- `POST /api/v1/agent/peer-traffic/report`
- `GET /api/v1/peer-traffic/summary`
- `GET /api/v1/peer-traffic/nodes/{node_id}`

### Node traffic accounting

- `GET /api/v1/node-traffic/summary`
- `GET /api/v1/node-traffic/nodes/{node_id}`
- `POST /api/v1/node-traffic/nodes/{node_id}/reset`
- `POST /api/v1/node-traffic/nodes/{node_id}/rollover`

## Backend Gaps Required by the Current Web UI

These are the missing backend modules or fields the current web UI expects.

### 1. Node accounting fields

The frontend expects these additive fields on node payloads:

- `registered_at: datetime | null`
- `traffic_limit_gb: float | null`
- `traffic_used_gb: float | null`

Current implementation note:

- `traffic_used_gb` is derived from the current node traffic accounting cycle.
- The current cycle is built from byte deltas received from the node agent via peer telemetry snapshots.
- It does not replace raw peer telemetry endpoints.
- Separate control endpoints now exist under `/api/v1/node-traffic/*` for reset and rollover operations.

### 2. Graph node metrics expansion

The frontend expects `graph.nodes[].metrics` to contain:

- `load_ratio`
- `peer_count`
- `ping_ms`

Current ONyX already exposes:

- `load_ratio`
- `ping_ms`
- `last_probe_at`

Missing additive field:

- `peer_count`

### 3. Registrations module

Required endpoints:

- `GET /api/v1/registrations`
- `POST /api/v1/registrations/{id}/approve`
- `POST /api/v1/registrations/{id}/reject`

Suggested registration object:

```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "created_at": "datetime",
  "referral_code": "string | null",
  "device_count": 1,
  "status": "pending | approved | rejected"
}
```

Filtering needed by UI:

- `?status=pending|approved|rejected`

### 4. Peers module

Required endpoints:

- `GET /api/v1/peers`
- `GET /api/v1/peers/{id}`
- `PUT /api/v1/peers/{id}/config`
- `POST /api/v1/peers/{id}/revoke`

Suggested peer object:

```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "node_id": "uuid",
  "registered_at": "datetime",
  "config_expires_at": "datetime | null",
  "last_ip": "string | null",
  "traffic_24h_mb": 0,
  "traffic_month_mb": 0,
  "config": "string | null"
}
```

Filtering needed by UI:

- `?node_id=uuid`
- `?username=string`

## Error Handling

Use the current ONyX backend style as the source of truth.

At this stage the frontend already works with FastAPI-style error responses and extracts messages from `detail`. Do not introduce a second custom error envelope unless there is a strong reason and the frontend is updated with it.

HTTP statuses expected by the UI:

- `401` — unauthenticated, frontend redirects to login
- `403` — forbidden
- `404` — object not found
- `409` — conflict
- `422` — validation error
- `500` — internal error

## Realtime

The frontend is already subscribed to:

- `WS /api/v1/ws/admin/events`

For the missing modules, emitting live events is useful but not required for the first backend pass.

Useful future event types:

```json
{ "type": "registration.approved", "payload": { "id": "uuid" } }
{ "type": "registration.rejected", "payload": { "id": "uuid" } }
{ "type": "peer.revoked", "payload": { "id": "uuid" } }
```

## Recommended Implementation Order

1. Add node accounting fields to `nodes`
2. Extend `/graph` to include `metrics.peer_count`
3. Add `Registration` model, migration, schemas, router
4. Add `Peer` model, migration, schemas, router
5. Wire the new modules into `onx/api/app.py`
6. Keep all existing routes unchanged

## Source of Truth Priority

When this prompt conflicts with the existing ONyX codebase:

1. Real routes and schemas in the repository win
2. Existing frontend expectations in `apps/web-admin/dist/index.html` come next
3. This prompt is only a synchronization and planning aid
