# ONX v0.2 Blueprint

## Status

Draft v0.2

Implemented delta: the repo now contains a functioning backend alpha slice beyond the original blueprint, including admin/client auth, DB-backed access rules, audit logs API, retention scheduler, topology/path APIs, native Ubuntu install/update scripts, and control-plane state export/import.

## Scope

This document defines the first implementation slice of ONX:

- repository structure
- backend process layout
- Python dependency set
- database schema v1
- first REST endpoints
- first delivery milestones

This document assumes the terms defined in [ONX_TECHNICAL_DESIGN.md](q:/MyVeryOwnAwgStS/docs/architecture/ONX_TECHNICAL_DESIGN.md).

## Implementation Strategy

The first ONX implementation must not try to replace the current legacy code in one pass.

Instead:

- keep the current legacy WGDashboard-based code operational
- add a new `onx/` implementation tree beside it
- build ONX as a clean backend-first subsystem
- reuse legacy AWG/WG operational knowledge only where it is proven and useful

The first production-worthy ONX flow should be:

1. register nodes
2. probe nodes over SSH
3. create AWG site-to-site link
4. validate link spec
5. render left and right configs
6. apply remotely over SSH
7. verify handshake
8. store applied state

No topology graph, no fancy UI, and no multi-driver matrix should block this first slice.

## Repository Layout

The repository should grow this structure:

```text
/docs
  /architecture
    ONX_TECHNICAL_DESIGN.md
    ONX_V0_2_BLUEPRINT.md
    ADR-0001-domain-model.md
    ADR-0002-driver-contract.md
    ADR-0003-ssh-first-deployment.md
    ADR-0004-control-plane-ha.md
    ADR-0005-interface-runtime-isolation.md
    ADR-0006-job-retry-and-cancel.md
    ADR-0007-job-target-locking.md
    ONX_MIGRATIONS.md

/onx
  /api
    __init__.py
    app.py
    deps.py
    errors.py
    routers/
      access_rules.py
      audit_logs.py
      health.py
      jobs.py
      nodes.py
      links.py
      balancers.py
      route_policies.py
      dns_policies.py
      geo_policies.py
      probes.py
      topology.py
      client_routing.py
      maintenance.py

  /core
    __init__.py
    config.py
    enums.py
    logging.py
    exceptions.py

  /db
    __init__.py
    base.py
    session.py
    models/
      node.py
      node_secret.py
      link.py
      link_endpoint.py
      route_policy.py
      dns_policy.py
      geo_policy.py
      balancer.py
      probe_result.py
      access_rule.py
      client_session.py
      client_probe.py
      job.py
      event_log.py
    repositories/
      nodes.py
      links.py
      jobs.py
    migrations/

  /schemas
    __init__.py
    common.py
    nodes.py
    links.py
    probes.py
    jobs.py
    drivers.py

  /services
    node_service.py
    link_service.py
    probe_service.py
    route_policy_service.py
    dns_policy_service.py
    geo_policy_service.py
    balancer_service.py
    secret_service.py
    event_log_service.py
    retention_service.py
    control_plane_state_service.py

  /drivers
    __init__.py
    base.py
    registry.py
    awg/
      driver.py
      schemas.py
      renderer.py
      templates/
    wg/
      driver.py
      schemas.py
      renderer.py

  /deploy
    ssh_client.py
    executor.py
    rollback.py
    command_builder.py
    remote_state.py

  /probes
    ping.py
    handshake.py
    speedtest.py

  /workers
    job_worker.py
    probe_scheduler.py
    retention_scheduler.py

  /tests
    conftest.py
    test_nodes_api.py
    test_links_api.py
    test_awg_driver.py
    test_ssh_deploy.py
```

## Process Layout

### Process 1: ONX API

Technology:

- FastAPI
- Uvicorn or Gunicorn/Uvicorn workers

Responsibilities:

- REST API
- orchestration entrypoints
- job creation
- schema validation
- read models

### Process 2: ONX Scheduler

Technology:

- APScheduler for v1

Responsibilities:

- background probes
- capability refresh
- delayed verification jobs
- deployment retries
- retention cleanup for history tables

Current implementation:

- `JobWorker`
- `ProbeScheduler`
- `RetentionScheduler`

### Process 3: Remote Execution

For v1 this is not a separate long-running process on the node.

It is SSH-based execution launched by the ONX API/Scheduler.

Later it may be replaced by an ONX agent.

## Control Plane Strategy in v0.2

The first implementation remains single-control.

That is intentional.

However, the project already reserves a migration path toward:

- three control-plane nodes
- replicated database state
- failover
- leader-controlled job execution

The accepted decision is recorded in:

- `ADR-0004-control-plane-ha.md`

Database sharding is not part of the near-term roadmap.

## Dependency Set

### Python Runtime

Target:

- Python 3.11 minimum
- Python 3.12 preferred

### Core Backend Dependencies

- `fastapi`
- `uvicorn[standard]`
- `pydantic`
- `pydantic-settings`
- `sqlalchemy`
- `alembic`
- `psycopg[binary]` or `sqlite` first, PostgreSQL preferred later
- `httpx`
- `jinja2`
- `pyyaml`
- `psutil`
- `orjson`
- `python-multipart`

### SSH and Remote Execution

- `asyncssh`

Reason:

- good fit for structured async remote execution
- easier future parallelism for node fan-out

Fallback if needed:

- `paramiko`

### Background and Scheduling

- `apscheduler`

### Security and Secrets

- `cryptography`
- `passlib` only if local auth grows later

### Testing

- `pytest`
- `pytest-asyncio`
- `httpx`
- `respx`
- `factory-boy`

### Optional Near-Term Dependencies

- `networkx` for backend topology derivation
- `iperf3` integration later, but not as a Python dependency requirement

## Database Choice

### v1 Recommendation

Start with:

- SQLite for local development
- PostgreSQL as the intended production backend

Reason:

- SQLite makes local iteration simple
- PostgreSQL is the correct long-term target for jobs, events, and topology state

The ORM and migration layer must be written so moving from SQLite to PostgreSQL is low-friction.

Current operational note:

- local development still supports SQLite
- native Ubuntu installer targets PostgreSQL by default

## Schema v1

The first schema should stay intentionally narrow.

### Table: `nodes`

Purpose:

- stores managed remote systems

Columns:

- `id` UUID PK
- `name` string unique
- `role` enum: `gateway | relay | egress | mixed`
- `management_address` string
- `ssh_host` string
- `ssh_port` integer
- `ssh_user` string
- `auth_type` enum: `password | private_key`
- `status` enum: `unknown | reachable | degraded | offline`
- `os_family` string nullable
- `os_version` string nullable
- `kernel_version` string nullable
- `last_seen_at` datetime nullable
- `created_at` datetime
- `updated_at` datetime

Notes:

- do not store raw passwords or private keys in this table

### Table: `node_secrets`

Purpose:

- stores references to encrypted credentials

Columns:

- `id` UUID PK
- `node_id` FK -> `nodes.id`
- `kind` enum: `ssh_password | ssh_private_key | transport_private_key | api_token`
- `secret_ref` string
- `created_at` datetime
- `updated_at` datetime

Notes:

- `secret_ref` may initially point to local encrypted storage
- later this can move to Vault or another secret backend

### Table: `node_capabilities`

Purpose:

- stores discovery results for available software and kernel/user-space support

Columns:

- `id` UUID PK
- `node_id` FK -> `nodes.id`
- `driver_name` string
- `supported` boolean
- `details_json` JSON
- `checked_at` datetime

Examples:

- AWG tools installed
- AWG kernel support present
- `wg` installed
- `openvpn` installed
- `xray` installed
- `iptables` or `nftables` mode

### Table: `links`

Purpose:

- normalized logical relationship between two nodes

Columns:

- `id` UUID PK
- `name` string unique
- `driver_name` string
- `topology_type` enum: `p2p | upstream | relay | balancer_member | service_edge`
- `left_node_id` FK -> `nodes.id`
- `right_node_id` FK -> `nodes.id`
- `state` enum: `planned | validating | applying | active | degraded | failed | deleted`
- `desired_spec_json` JSON
- `applied_spec_json` JSON nullable
- `health_summary_json` JSON nullable
- `created_at` datetime
- `updated_at` datetime

### Table: `link_endpoints`

Purpose:

- per-side rendered and applied attachment data

Columns:

- `id` UUID PK
- `link_id` FK -> `links.id`
- `node_id` FK -> `nodes.id`
- `side` enum: `left | right`
- `interface_name` string nullable
- `listen_port` integer nullable
- `address_v4` string nullable
- `address_v6` string nullable
- `mtu` integer nullable
- `endpoint` string nullable
- `public_key` string nullable
- `private_key_secret_ref` string nullable
- `rendered_config` text nullable
- `applied_state_json` JSON nullable
- `created_at` datetime
- `updated_at` datetime

### Table: `route_policies`

Purpose:

- stores routing intent for ingress traffic

Columns:

- `id` UUID PK
- `node_id` FK -> `nodes.id`
- `name` string
- `ingress_interface` string
- `action` enum: `direct | next_hop | balancer`
- `target_interface` string nullable
- `target_gateway` string nullable
- `balancer_id` FK nullable
- `routed_networks` JSON
- `excluded_networks` JSON
- `table_id` integer
- `rule_priority` integer
- `firewall_mark` integer
- `masquerade` boolean
- `enabled` boolean
- `applied_state` JSON nullable
- `last_applied_at` datetime nullable
- `created_at` datetime
- `updated_at` datetime

### Table: `dns_policies`

Purpose:

- stores forced local DNS capture behavior

Columns:

- `id` UUID PK
- `route_policy_id` FK -> `route_policies.id`
- `enabled` boolean
- `dns_address` string
- `capture_protocols` JSON
- `capture_ports` JSON
- `exceptions_networks` JSON
- `applied_state` JSON nullable
- `last_applied_at` datetime nullable
- `created_at` datetime
- `updated_at` datetime

### Table: `geo_policies`

Purpose:

- stores per-country route handling attached to one route policy

Columns:

- `id` UUID PK
- `route_policy_id` FK -> `route_policies.id`
- `country_code` string
- `mode` enum: `direct | multihop`
- `source_url_template` string
- `enabled` boolean
- `created_at` datetime
- `updated_at` datetime

### Table: `balancers`

Purpose:

- defines a logical balancing target over links or egress objects

Columns:

- `id` UUID PK
- `node_id` FK -> `nodes.id`
- `name` string
- `method` enum: `random | leastload | leastping`
- `members` JSON
- `enabled` boolean
- `state_json` JSON nullable
- `created_at` datetime
- `updated_at` datetime

### Table: `probe_results`

Purpose:

- stores health and measurement history

Columns:

- `id` UUID PK
- `probe_type` enum: `ping | interface_load`
- `source_node_id` UUID nullable
- `balancer_id` UUID nullable
- `member_interface` string nullable
- `status` enum: `success | failed | degraded`
- `metrics_json` JSON
- `error_text` text nullable
- `created_at` datetime

### Table: `access_rules`

Purpose:

- stores DB-backed overrides for admin/control-plane permissions

Columns:

- `id` UUID PK
- `permission_key` string unique
- `description` text nullable
- `allowed_roles_json` JSON
- `enabled` boolean
- `created_at` datetime
- `updated_at` datetime

### Table: `client_sessions`

Purpose:

- stores client-to-ingress routing session state for ingress selection and rebind

### Table: `client_probes`

Purpose:

- stores client-submitted ingress probe measurements used for best-ingress decisions

### Table: `jobs`

Purpose:

- tracks validation, apply, rollback, and probe work

Columns:

- `id` UUID PK
- `kind` enum: `discover | validate | render | apply | destroy | probe | rollback`
- `target_type` enum: `node | link | policy | balancer`
- `target_id` UUID
- `state` enum: `pending | running | succeeded | failed | rolled_back`
- `request_payload_json` JSON
- `result_payload_json` JSON nullable
- `error_text` text nullable
- `started_at` datetime nullable
- `finished_at` datetime nullable
- `created_at` datetime

### Table: `event_logs`

Purpose:

- operator-readable audit trail

Columns:

- `id` UUID PK
- `level` enum: `info | warning | error`
- `entity_type` string
- `entity_id` UUID nullable
- `message` text
- `details_json` JSON nullable
- `created_at` datetime

## Schema Priorities

Must exist in the first migration:

- `nodes`
- `node_secrets`
- `node_capabilities`
- `links`
- `link_endpoints`
- `jobs`
- `event_logs`

Can be added immediately after:

- `route_policies`
- `dns_policies`
- `geo_policies`
- `balancers`
- `probe_results`
- `access_rules`
- `client_sessions`
- `client_probes`

## Driver Support Matrix for v0.2

### Mandatory in First Working Slice

- `awg`

### Optional in Same Structural Contract, but Not Yet Implemented

- `wg`
- `openvpn`
- `ikev2_ipsec`

The point is to stabilize the contract with one real driver first.

## First Driver: AWG

The AWG driver should be the first real implementation because:

- it already exists in the current operational domain
- the project has live troubleshooting knowledge around it
- it exercises key challenges:
  - interface rendering
  - peer creation
  - endpoint management
  - obfuscation parameters
  - site-to-site handshake verification

### AWG Driver Responsibilities

- validate link spec
- generate left and right endpoint config
- detect kernel or userspace mode
- apply config remotely
- save and reload if needed
- read public key, transfer, endpoint, latest handshake
- rollback remote changes on partial failure

## First REST API Surface

Version prefix:

- `/api/v1`

### Health

#### `GET /api/v1/health`

Purpose:

- process health

Response:

```json
{
  "status": "ok",
  "service": "onx-api",
  "version": "0.1.0"
}
```

#### `GET /api/v1/health/worker`

Purpose:

- worker and scheduler runtime snapshot

### Nodes

#### `GET /api/v1/nodes`

Purpose:

- list managed nodes

#### `POST /api/v1/nodes`

Purpose:

- create managed node

Request:

```json
{
  "name": "gate-eu-1",
  "role": "gateway",
  "management_address": "45.144.31.221",
  "ssh_host": "45.144.31.221",
  "ssh_port": 22,
  "ssh_user": "root",
  "auth": {
    "type": "password",
    "value": "secret"
  }
}
```

Response:

```json
{
  "id": "uuid",
  "name": "gate-eu-1",
  "status": "unknown"
}
```

#### `GET /api/v1/nodes/{node_id}`

Purpose:

- fetch one node

#### `PATCH /api/v1/nodes/{node_id}`

Purpose:

- update mutable node fields

#### `POST /api/v1/nodes/{node_id}/discover`

Purpose:

- run SSH discovery and capability detection

Response:

```json
{
  "job_id": "uuid",
  "state": "pending"
}
```

#### `GET /api/v1/nodes/{node_id}/capabilities`

Purpose:

- fetch latest capability snapshot

### Links

#### `GET /api/v1/links`

Purpose:

- list normalized links

#### `POST /api/v1/links`

Purpose:

- create a new link definition

Minimal first supported payload:

```json
{
  "name": "gate1-back1-awg",
  "driver_name": "awg",
  "topology_type": "p2p",
  "left_node_id": "uuid-left",
  "right_node_id": "uuid-right",
  "spec": {
    "mode": "site_to_site",
    "left": {
      "interface_name": "awg1",
      "listen_port": 8443,
      "address_v4": "10.77.77.1/30"
    },
    "right": {
      "interface_name": "awg3",
      "listen_port": 8444,
      "address_v4": "10.77.77.2/30"
    },
    "peer": {
      "persistent_keepalive": 21,
      "mtu": 1420
    },
    "awg_obfuscation": {
      "jc": 5,
      "jmin": 49,
      "jmax": 998,
      "s1": 17,
      "s2": 43,
      "s3": 86,
      "s4": 55,
      "h1": 474868796,
      "h2": 613073023,
      "h3": 931487895,
      "h4": 1155209138
    }
  }
}
```

#### `GET /api/v1/links/{link_id}`

Purpose:

- fetch one link with endpoints and latest health

#### `POST /api/v1/links/{link_id}/validate`

Purpose:

- validate link spec and capability compatibility without applying

Response:

```json
{
  "valid": true,
  "warnings": [],
  "render_preview": {
    "left": "...",
    "right": "..."
  }
}
```

#### `POST /api/v1/links/{link_id}/apply`

Purpose:

- deploy link to both nodes

Response:

```json
{
  "job_id": "uuid",
  "state": "pending"
}
```

#### `POST /api/v1/links/{link_id}/destroy`

Purpose:

- remove deployed link from both nodes

#### `GET /api/v1/links/{link_id}/status`

Purpose:

- current link status and health

Response:

```json
{
  "state": "active",
  "health": {
    "handshake": "ok",
    "left_to_right_ping": "ok",
    "latest_handshake_seconds": 12
  }
}
```

### Jobs

#### `GET /api/v1/jobs`

Purpose:

- list latest jobs

#### `GET /api/v1/jobs/{job_id}`

Purpose:

- fetch job execution result

#### `POST /api/v1/jobs/{job_id}/cancel`

Purpose:

- request cooperative cancellation

#### `POST /api/v1/jobs/{job_id}/retry-now`

Purpose:

- requeue an eligible failed or pending job immediately

### Probes

#### `GET /api/v1/probes/results`

Purpose:

- list stored balancer/topology probe results

#### `POST /api/v1/probes/balancers/{id}/run`

Purpose:

- run fresh ping/interface-load probes for balancer members

### Access Rules

#### `GET /api/v1/access-rules`

- list DB overrides

#### `GET /api/v1/access-rules/matrix`

- effective permission matrix

#### `PUT /api/v1/access-rules/{permission_key}`

- upsert permission override

#### `DELETE /api/v1/access-rules/{permission_key}`

- delete override and fall back to defaults

### Audit Logs

#### `GET /api/v1/audit-logs`

- read control-plane audit events

### Maintenance

#### `GET /api/v1/maintenance/retention`

- show retention policy

#### `POST /api/v1/maintenance/cleanup`

- run immediate cleanup for `probe_results` and `event_logs`

### Client Routing

#### `POST /api/v1/bootstrap`

- register or refresh client session bootstrap context

#### `POST /api/v1/probe`

- submit client-side ingress measurements

#### `POST /api/v1/best-ingress`

- pick best ingress and optionally a planned path

#### `POST /api/v1/session-rebind`

- update routing session when a better ingress is selected

### Topology

#### `GET /api/v1/graph`

- graph payload for backend-driven topology view

#### `POST /api/v1/paths/plan`

- shortest-path planning by weighted metrics

## Pydantic Schema Groups

The following schema groups should exist from the first backend commit.

### `schemas/nodes.py`

- `NodeCreate`
- `NodeUpdate`
- `NodeRead`
- `NodeCapabilityRead`
- `NodeDiscoverResponse`

### `schemas/links.py`

- `LinkCreate`
- `LinkRead`
- `LinkValidateRequest`
- `LinkValidateResponse`
- `LinkApplyResponse`
- `LinkStatusRead`
- `AWGLinkSpec`
- `AWGEndpointSpec`
- `AWGObfuscationSpec`

### `schemas/jobs.py`

- `JobRead`
- `JobListRead`

### `schemas/probes.py`

- `ProbeRequest`
- `ProbeResultRead`

## Service Layer Responsibilities

### `NodeService`

Responsibilities:

- create nodes
- update nodes
- resolve auth refs
- trigger discovery
- persist capability state

### `LinkService`

Responsibilities:

- create normalized link objects
- resolve driver
- validate spec
- create apply jobs
- read status

### `DeploymentService`

Responsibilities:

- call driver render
- call remote executor
- update applied state
- trigger rollback when needed

### `ProbeService`

Responsibilities:

- create and store probe results
- map probe outputs to health summary

### `RetentionService`

Responsibilities:

- apply retention policy to history tables
- support both scheduled and manual cleanup

### `ControlPlaneStateService`

Responsibilities:

- export deterministic backup of core control-plane objects
- import and replace state safely enough for alpha recovery workflows
- avoid exporting management secrets unless explicitly requested

### `SecretService`

Responsibilities:

- store and retrieve encrypted secrets
- never expose raw secrets back to read APIs

## SSH-First Deployment Rules

For v0.2:

- every remote action must be explicit and logged
- commands must be idempotent where practical
- config preview must exist before apply
- apply must stop on the first irreversible failure
- rollback must be attempted automatically on failed two-sided link deployment

Examples of rollback conditions:

- left config written, right config failed
- both configs written, handshake never appears
- remote interface started but health checks fail

## AWG Site-to-Site Happy Path

The first end-to-end feature should follow this pipeline:

1. user creates two nodes
2. user runs discovery on both nodes
3. user creates AWG link spec
4. API validates:
   - nodes reachable
   - AWG supported on both nodes
   - interface names not conflicting
   - subnets valid
   - ports valid
   - obfuscation params valid
5. API renders left and right configs
6. API returns preview
7. user applies
8. deployment job:
   - write config left
   - write config right
   - bring up left
   - bring up right
   - verify handshake
   - persist applied state
9. status endpoint shows active link

## Milestone Plan

### Milestone A: Backend Skeleton

Deliver:

- `onx/` package
- FastAPI app
- config loader
- SQLAlchemy base
- Alembic init
- `/api/v1/health`

### Milestone B: Nodes

Deliver:

- node CRUD
- secret storage
- SSH discovery
- capability records

### Milestone C: AWG Link Spec and Validation

Deliver:

- AWG schemas
- driver interface
- validation-only flow
- config preview

### Milestone D: AWG Deployment

Deliver:

- SSH remote executor
- apply job
- rollback path
- handshake verification

### Milestone E: First Probe Layer

Deliver:

- ping probe
- handshake probe
- health summary on link

Only after these milestones should the project move to:

- route policies
- DNS policies
- balancers
- topology graph
- additional drivers

## Current Alpha Delta

Beyond the original milestone sequence, the current alpha backend already includes:

- route policies + deterministic `apply-planned`
- DNS and geo policies
- balancers
- topology graph and path planner
- client-routing protocol
- client/admin auth layers
- DB-backed admin access rules
- audit logs API
- retention scheduler and manual cleanup API
- control-plane state export/import
- native Ubuntu install/update scripts with TLS helpers

## Immediate Next Work Item

The next implementation artifact after this blueprint should be:

- `ADR-0001-domain-model.md`

or, if coding starts immediately:

- `onx/` backend skeleton with FastAPI, settings, SQLAlchemy base, and the `Node` schema/API.
