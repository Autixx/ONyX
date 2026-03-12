# ONyX Web UI Handoff

## Purpose

This document is the frontend handoff for building the first ONyX web UI on top of the
existing control-plane API.

It is written for an implementation agent or frontend engineer who will build the UI
without changing the backend contract by default.

The goal is not to redesign ONyX.

The goal is to attach a usable operator UI to the API which already exists.

## Current Readiness Summary

The backend foundation for a web UI is ready.

What is already ready:

- stable API prefix: `/api/v1`
- structured REST endpoints grouped by domain
- native Ubuntu deployment
- nginx-based HTTPS wrapper
- admin auth for control-plane API
- client auth for client-routing API
- DB-backed ACL rules
- jobs, retries, events, audit logs
- topology graph and path planner

What is not implemented yet:

- browser-specific auth/session flow
- user accounts for operators
- refresh-token or cookie auth
- CORS middleware for cross-origin SPA hosting
- websocket/SSE push updates
- static frontend hosting inside ONyX

Implication:

- The first web UI should be an operator UI using the existing admin bearer token or admin JWT.
- The safest deployment model is same-host or reverse-proxied same-origin UI.

## Deployment and TLS

### Backend runtime

Default ONyX deployment:

- service: `onx-api.service`
- local bind: `127.0.0.1:8081`
- API prefix: `/api/v1`
- health endpoint: `/api/v1/health`

### TLS

HTTPS is already supported through:

- [install_onx_ubuntu.sh](Q:\ONyX_export\scripts\install_onx_ubuntu.sh)
- [setup_onx_tls_openssl.sh](Q:\ONyX_export\scripts\setup_onx_tls_openssl.sh)

Current TLS model:

- nginx reverse proxy in front of ONyX
- self-signed OpenSSL certificate by default
- backend stays local by default (`127.0.0.1`)

This is sufficient for the first operator web UI.

### Important browser constraint

There is currently no CORS middleware in FastAPI.

Therefore the first UI should be deployed in one of these ways:

1. same origin behind nginx
2. dev server with reverse proxy to ONyX
3. separate origin only after explicit backend CORS support is added

Do not assume the API is cross-origin ready.

## Auth Model

### Admin UI auth

The operator web UI should use the admin API auth surface.

Supported modes:

- `disabled`
- `token`
- `jwt`
- `token_or_jwt`

Current default install mode:

- admin auth: `token`
- admin token stored in `/etc/onx/admin-auth.txt`

Admin API auth is enforced for:

- `/api/v1/health/worker`
- `/api/v1/audit-logs`
- `/api/v1/jobs/*`
- `/api/v1/nodes/*`
- `/api/v1/links/*`
- `/api/v1/balancers/*`
- `/api/v1/route-policies/*`
- `/api/v1/dns-policies/*`
- `/api/v1/geo-policies/*`
- `/api/v1/probes/*`
- `/api/v1/graph`
- `/api/v1/paths/plan`
- `/api/v1/access-rules*`
- `/api/v1/maintenance/*`

Public:

- `/api/v1/health`

### Admin UI auth recommendation

For the first web UI:

- accept manual admin bearer token input
- store it in memory or local storage only if explicitly desired
- send `Authorization: Bearer <token>`
- on `401`, redirect to auth input screen
- on `403`, show permission denial with endpoint/action context

Do not invent a username/password login page unless backend support is added.

### ACL model

Admin API permissions are not just read/write globally.

They resolve to permission keys such as:

- `nodes.read`
- `nodes.write`
- `links.read`
- `links.write`
- `route_policies.read`
- `route_policies.write`
- `topology.read`
- `topology.plan`
- `access_rules.read`
- `access_rules.write`

The UI must be prepared for role-based partial access.

Example:

- user can read nodes but cannot create or delete them
- user can read jobs but cannot cancel them

If an action returns `403`, the UI should disable or hide that action after the first failed capability fetch.

## API Shape

There are currently 14 router groups:

- `health`
- `client_routing`
- `access_rules`
- `audit_logs`
- `jobs`
- `nodes`
- `links`
- `balancers`
- `route_policies`
- `dns_policies`
- `geo_policies`
- `probes`
- `topology`
- `maintenance`

FastAPI default docs should also exist:

- `/docs`
- `/openapi.json`

Treat them as implementation aids, not as the primary product contract.

## UI Scope Recommendation

The first web UI should cover operator/admin workflows only.

Recommended top-level sections:

1. Dashboard
2. Nodes
3. Links
4. Policies
5. Jobs
6. Audit / Access
7. Topology
8. Tools / Debug

This mirrors the existing TUI and current API grouping.

## Screen Map and Backend Mapping

### 1. Dashboard

Purpose:

- operator landing page
- service health
- worker state
- retention info
- latest jobs
- recent audit events

Recommended data sources:

- `GET /api/v1/health`
- `GET /api/v1/health/worker`
- `GET /api/v1/maintenance/retention`
- `GET /api/v1/jobs`
- `GET /api/v1/audit-logs?limit=20`

Recommended widgets:

- API status
- worker status
- jobs summary by state
- latest failed jobs
- recent audit events
- retention policy summary

### 2. Nodes

Purpose:

- lifecycle of managed nodes
- onboarding
- capability inspection
- runtime bootstrap
- AWG readiness verification

Endpoints:

- `GET /api/v1/nodes`
- `POST /api/v1/nodes`
- `GET /api/v1/nodes/{node_id}`
- `PATCH /api/v1/nodes/{node_id}`
- `DELETE /api/v1/nodes/{node_id}`
- `PUT /api/v1/nodes/{node_id}/secret`
- `GET /api/v1/nodes/{node_id}/capabilities`
- `POST /api/v1/nodes/{node_id}/discover`
- `POST /api/v1/nodes/{node_id}/bootstrap-runtime`

#### Node list view

Fields to show:

- `name`
- `role`
- `status`
- `management_address`
- `ssh_host`
- `ssh_user`
- `auth_type`
- `os_family`
- `os_version`
- `kernel_version`
- `last_seen_at`

Recommended row actions:

- inspect
- edit
- delete
- discover
- bootstrap runtime
- view capabilities
- AWG readiness check

#### Node create form

Payload:

```json
{
  "name": "node-1",
  "role": "mixed",
  "management_address": "203.0.113.10",
  "ssh_host": "203.0.113.10",
  "ssh_port": 22,
  "ssh_user": "root",
  "auth_type": "password"
}
```

Then immediately call:

- `PUT /api/v1/nodes/{node_id}/secret`

Secret payload:

```json
{
  "kind": "ssh_password",
  "value": "secret"
}
```

or:

```json
{
  "kind": "ssh_private_key",
  "value": "-----BEGIN OPENSSH PRIVATE KEY-----..."
}
```

Important:

- secrets are write-only in practical UI terms
- UI should never try to re-display secret plaintext after submit

#### AWG readiness check

This is not a dedicated backend endpoint yet.

The UI should derive it from `GET /nodes/{id}/capabilities`.

Required capabilities for AWG s2s:

- `awg`
- `awg_quick`
- `amneziawg_go`
- `iptables`
- `ipset`
- `systemctl`
- `onx_link_runtime`

If any are missing, show `NOT READY`.

### 3. Links

Purpose:

- create site-to-site transport edges between two managed nodes
- validate specs before apply
- apply transport configuration through ONyX jobs

Endpoints:

- `GET /api/v1/links`
- `POST /api/v1/links`
- `GET /api/v1/links/{link_id}`
- `POST /api/v1/links/{link_id}/validate`
- `POST /api/v1/links/{link_id}/apply`

#### Link create form

Current driver support:

- `awg`

Current topology values:

- `p2p`
- `upstream`
- `relay`
- `balancer_member`
- `service_edge`

For current alpha UI, support only:

- `driver_name = "awg"`
- `topology_type = "p2p"`

Recommended create wizard:

1. select left node
2. select right node
3. configure left endpoint
4. configure right endpoint
5. configure peer params
6. configure AWG obfuscation
7. submit create
8. run validate
9. run apply

Core payload shape:

```json
{
  "name": "awg-link-a-b",
  "driver_name": "awg",
  "topology_type": "p2p",
  "left_node_id": "uuid-left",
  "right_node_id": "uuid-right",
  "spec": {
    "mode": "site_to_site",
    "left": {
      "interface_name": "awg10",
      "listen_port": 8443,
      "address_v4": "10.77.77.1/30",
      "address_v6": null,
      "mtu": 1420,
      "endpoint_host": "203.0.113.10"
    },
    "right": {
      "interface_name": "awg11",
      "listen_port": 8444,
      "address_v4": "10.77.77.2/30",
      "address_v6": null,
      "mtu": 1420,
      "endpoint_host": "203.0.113.11"
    },
    "peer": {
      "persistent_keepalive": 21,
      "mtu": 1420,
      "left_allowed_ips": ["10.77.77.2/32"],
      "right_allowed_ips": ["10.77.77.1/32"]
    },
    "awg_obfuscation": {
      "jc": 4,
      "jmin": 40,
      "jmax": 120,
      "s1": 20,
      "s2": 40,
      "s3": 80,
      "s4": 120,
      "h1": 10101,
      "h2": 20202,
      "h3": 30303,
      "h4": 40404
    }
  }
}
```

#### Validate flow

After create:

- call `POST /api/v1/links/{id}/validate`

The UI should display:

- `valid`
- `warnings`
- `render_preview`
- node capabilities used in validation

#### Apply flow

Apply returns a `JobRead`.

The UI must:

1. enqueue apply
2. store returned `job_id`
3. poll `GET /api/v1/jobs/{job_id}`
4. display `current_step`, `state`, `error_text`
5. show result payload on success/failure

No websocket/SSE exists, so use polling.

### 4. Policies

Subsections:

- route policies
- DNS policies
- geo policies
- balancers

#### 4.1 Route Policies

Endpoints:

- `GET /api/v1/route-policies`
- `POST /api/v1/route-policies`
- `GET /api/v1/route-policies/{policy_id}`
- `GET /api/v1/route-policies/{policy_id}/plan`
- `PATCH /api/v1/route-policies/{policy_id}`
- `DELETE /api/v1/route-policies/{policy_id}`
- `POST /api/v1/route-policies/{policy_id}/apply`
- `POST /api/v1/route-policies/{policy_id}/apply-planned`

Current actions:

- `direct`
- `next_hop`
- `balancer`

Important fields:

- `node_id`
- `name`
- `ingress_interface`
- `action`
- `target_interface`
- `target_gateway`
- `balancer_id`
- `routed_networks`
- `excluded_networks`
- `table_id`
- `rule_priority`
- `firewall_mark`
- `masquerade`
- `enabled`

UI recommendation:

- create a form-based editor, not a raw JSON text area
- show planned scripts from `/plan`
- support deterministic `apply-planned`

If using `apply-planned`, the UI must send:

```json
{
  "plan_fingerprint": "<64-char-fingerprint>",
  "enforce_snapshot": true
}
```

#### 4.2 DNS Policies

Endpoints:

- `GET /api/v1/dns-policies`
- `POST /api/v1/dns-policies`
- `GET /api/v1/dns-policies/{dns_policy_id}`
- `PATCH /api/v1/dns-policies/{dns_policy_id}`
- `DELETE /api/v1/dns-policies/{dns_policy_id}`
- `POST /api/v1/dns-policies/{dns_policy_id}/apply`

Core fields:

- `route_policy_id`
- `enabled`
- `dns_address`
- `capture_protocols`
- `capture_ports`
- `exceptions_networks`

This maps to the local DNS interception feature.

#### 4.3 Geo Policies

Endpoints:

- `GET /api/v1/geo-policies`
- `POST /api/v1/geo-policies`
- `GET /api/v1/geo-policies/{geo_policy_id}`
- `PATCH /api/v1/geo-policies/{geo_policy_id}`
- `DELETE /api/v1/geo-policies/{geo_policy_id}`
- `POST /api/v1/geo-policies/{geo_policy_id}/apply`

Core fields:

- `route_policy_id`
- `country_code`
- `mode`
- `source_url_template`
- `enabled`

Current modes:

- `direct`
- `multihop`

UI recommendation:

- make country selection explicit and searchable
- treat `source_url_template` as advanced field

#### 4.4 Balancers

Endpoints:

- `GET /api/v1/balancers`
- `POST /api/v1/balancers`
- `GET /api/v1/balancers/{balancer_id}`
- `PATCH /api/v1/balancers/{balancer_id}`
- `DELETE /api/v1/balancers/{balancer_id}`
- `POST /api/v1/balancers/{balancer_id}/pick`
- `POST /api/v1/probes/balancers/{balancer_id}/run`

Methods:

- `random`
- `leastload`
- `leastping`

Member shape:

```json
{
  "interface_name": "awg1",
  "gateway": null,
  "ping_target": "1.1.1.1",
  "weight": 1
}
```

UI recommendation:

- support member table editor
- show current `state_json`
- expose `pick` and `run probes` as operator actions

### 5. Jobs

Purpose:

- visibility into background operations
- cancellation / retry controls
- failure inspection

Endpoints:

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/locks`
- `POST /api/v1/jobs/locks/cleanup`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry-now`
- `POST /api/v1/jobs/{job_id}/force-cancel`
- `GET /api/v1/jobs/{job_id}/events`

Recommended jobs table columns:

- `id`
- `kind`
- `target_type`
- `target_id`
- `state`
- `attempt_count`
- `current_step`
- `worker_owner`
- `created_at`
- `started_at`
- `finished_at`

Detail view should also show:

- `request_payload_json`
- `result_payload_json`
- `error_text`
- `events`

### 6. Audit / Access

#### 6.1 Audit Logs

Endpoint:

- `GET /api/v1/audit-logs?limit=...`

Useful columns:

- `created_at`
- `level`
- `entity_type`
- `entity_id`
- `message`

Use this page for:

- ACL changes
- auth rotation events
- maintenance runs

#### 6.2 Access Rules

Endpoints:

- `GET /api/v1/access-rules`
- `GET /api/v1/access-rules/matrix`
- `PUT /api/v1/access-rules/{permission_key}`
- `DELETE /api/v1/access-rules/{permission_key}`

UI recommendation:

- one table for effective matrix
- one editor modal for upsert
- do not hide the source distinction:
  - default
  - db override

### 7. Topology

Endpoints:

- `GET /api/v1/graph`
- `POST /api/v1/paths/plan`

#### Graph

Use this as the data source for the network map.

The UI should not invent graph edges client-side.

Use backend `graph` output as source of truth.

#### Path planner

Payload shape:

```json
{
  "source_node_id": "uuid-a",
  "destination_node_id": "uuid-b",
  "max_hops": 8,
  "require_active_links": true,
  "avoid_node_ids": [],
  "latency_weight": 1.0,
  "load_weight": 1.2,
  "loss_weight": 1.5
}
```

UI recommendation:

- source node selector
- destination node selector
- advanced weights drawer
- show returned path nodes and derived score

### 8. System / Maintenance

Endpoints:

- `GET /api/v1/health`
- `GET /api/v1/health/worker`
- `GET /api/v1/maintenance/retention`
- `POST /api/v1/maintenance/cleanup`
- `GET /api/v1/probes/results`

This is enough for a simple operator dashboard and maintenance page.

## Client-Routing Endpoints

These are not primary operator UI endpoints.

They are for future client/runtime integration:

- `POST /api/v1/bootstrap`
- `POST /api/v1/probe`
- `POST /api/v1/best-ingress`
- `POST /api/v1/session-rebind`

The operator UI may expose them only as debug screens.

Do not make them central to the first admin UI.

## Error Handling Contract

### Expected status codes

- `200` / `201` / `202` - success
- `204` - successful delete
- `400` - invalid payload
- `401` - missing or invalid bearer token
- `403` - insufficient role / ACL denial
- `404` - missing entity
- `409` - conflict, often due to active jobs or duplicate names
- `429` - rate limited client-routing endpoint
- `503` - temporary service/access resolution issue

### UI behavior

- `401`: force auth re-entry
- `403`: show permission error, do not loop-retry
- `409`: show conflict detail inline
- `202`: switch to job tracking UI

### Job-driven actions

The UI must distinguish two action types:

1. immediate CRUD response
2. async job enqueue response

Async examples:

- node discovery
- runtime bootstrap
- link apply
- policy apply
- geo apply
- DNS apply

For these, success means:

- enqueue succeeded
- then job state becomes `succeeded`

Not merely `202`.

## Polling Strategy

There is no push channel.

Recommended polling:

- job detail page: every `2-3s`
- jobs list while active jobs exist: every `5s`
- dashboard widgets: every `10-30s`
- graph page: manual refresh or every `15-30s`

Stop polling when:

- page is hidden
- job reaches terminal state
- user navigates away

## UI Technology Guidance

The backend does not force a frontend framework.

A SPA is fine.

What matters:

- typed API client
- polling support
- sane form handling
- graph rendering
- dark operator UI

The frontend should not:

- generate payloads ad hoc without schema alignment
- invent hidden backend state
- assume cross-origin API support
- assume websocket updates

## Recommended Initial Route Tree

Suggested frontend routes:

- `/signin`
- `/dashboard`
- `/nodes`
- `/nodes/:id`
- `/links`
- `/links/:id`
- `/policies/routes`
- `/policies/dns`
- `/policies/geo`
- `/policies/balancers`
- `/jobs`
- `/jobs/:id`
- `/audit`
- `/access-rules`
- `/topology`
- `/tools/api-debug`

## Recommended Delivery Order

Build in this order:

1. auth input shell
2. dashboard
3. nodes
4. jobs
5. links
6. route policies
7. DNS / geo / balancers
8. topology graph
9. audit / access
10. optional API debug screens

This order gives immediate operator value without blocking on the graph UI.

## Known Backend Gaps Relevant to UI

These are real current gaps, not frontend bugs:

1. no browser-native login/session flow
2. no CORS middleware
3. no websocket/SSE
4. no built-in static UI serving
5. no dedicated endpoint for AWG readiness; derive it from capabilities
6. some create/update flows are still raw and schema-heavy
7. auth rotation is currently script/TUI-driven, not API-driven

Frontend should work around these gaps, not hide them.

## Backend-Safe Assumptions for UI

Safe assumptions:

- IDs are UUID strings
- timestamps are ISO-like datetime values
- async operations use jobs
- transport driver currently means AWG for link creation
- admin token auth is the default operator auth
- TLS can be terminated by nginx on the same host

Unsafe assumptions:

- that all endpoints support pagination
- that all actions are synchronous
- that cross-origin browser access is supported
- that create/update schemas will accept arbitrary extra fields
- that frontend may skip validate-before-apply for links

## What Claude Should Not Do

- do not redesign backend routes
- do not invent session auth
- do not assume cookies
- do not assume GraphQL
- do not invent separate “node readiness” backend routes unless requested
- do not merge client-routing flows into operator UI navigation as a primary feature

## What Claude Can Build Immediately

Without backend changes, Claude can build:

- operator auth shell using bearer token
- full admin dashboard
- nodes CRUD UI
- discovery/bootstrap/capabilities workflows
- AWG readiness derived UI
- links create/validate/apply UI
- policies CRUD/apply UI
- jobs monitoring UI
- topology graph UI
- audit/ACL UI

That is enough for a serious first operator web interface.
