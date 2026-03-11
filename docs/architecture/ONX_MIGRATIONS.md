# ONX Migrations

## Baseline

ONX uses Alembic as the schema source of truth.

- config: [alembic.ini](q:/MyVeryOwnAwgStS/alembic.ini)
- env: `onx/alembic/env.py`
- versions: `onx/alembic/versions/`

`init_db()` now runs `upgrade head` through Alembic.

## Local Commands

Run from repo root:

```bash
python -m alembic -c alembic.ini upgrade head
```

Create new revision:

```bash
python -m alembic -c alembic.ini revision -m "your message"
```

Downgrade one revision:

```bash
python -m alembic -c alembic.ini downgrade -1
```

## Notes

- `alembic.ini` is tracked in repo and explicitly unignored in `.gitignore`.
- current baseline revision includes jobs retry/cancel fields and extended job states.
- `0002_add_job_locks` adds persistent target-scoped locks for worker concurrency control.
- `0003_add_route_policies` adds route policy storage with `direct` / `next_hop` actions and applied state tracking.
- `0004_add_dns_policies` adds per-route-policy DNS capture settings and applied state tracking.
- `0005_add_geo_policies` adds per-route-policy geo rules (`direct`/`multihop`) with country-based CIDR source templates.
- `0006_add_balancers_and_route_policy_balancer` adds balancers (`random`/`leastload`/`leastping`) and route policy action `balancer` with `balancer_id`.
- `0007_add_probe_results` adds persisted probe history for member ping/load metrics used by balancer selection.
- `0008_add_client_routing_protocol` adds `client_sessions` and `client_probes` for client-driven ingress selection.
- `0009_add_access_rules` adds DB-backed API access rule overrides by `permission_key -> allowed_roles`.
- jobs API supports:
  - `POST /api/v1/jobs/{id}/cancel`
  - `POST /api/v1/jobs/{id}/retry-now`
  - `POST /api/v1/jobs/{id}/force-cancel` (only for expired-lease running jobs)
  - `GET /api/v1/jobs/locks`
  - `POST /api/v1/jobs/locks/cleanup`
- health API supports:
  - `GET /api/v1/health/worker` (worker runtime snapshot + queue/lock stats)
- route policy API supports:
  - `GET /api/v1/route-policies`
  - `POST /api/v1/route-policies`
  - `GET /api/v1/route-policies/{id}`
  - `GET /api/v1/route-policies/{id}/plan` (preview rendered scripts and resolved egress target)
  - `PATCH /api/v1/route-policies/{id}`
  - `DELETE /api/v1/route-policies/{id}`
  - `POST /api/v1/route-policies/{id}/apply` (enqueues policy apply job)
  - `POST /api/v1/route-policies/{id}/apply-planned` (enqueues deterministic apply using plan fingerprint + snapshot)
- dns policy API supports:
  - `GET /api/v1/dns-policies`
  - `POST /api/v1/dns-policies`
  - `GET /api/v1/dns-policies/{id}`
  - `PATCH /api/v1/dns-policies/{id}`
  - `DELETE /api/v1/dns-policies/{id}`
  - `POST /api/v1/dns-policies/{id}/apply` (enqueues apply for parent route policy)
- geo policy API supports:
  - `GET /api/v1/geo-policies`
  - `POST /api/v1/geo-policies`
  - `GET /api/v1/geo-policies/{id}`
  - `PATCH /api/v1/geo-policies/{id}`
  - `DELETE /api/v1/geo-policies/{id}`
  - `POST /api/v1/geo-policies/{id}/apply` (enqueues apply for parent route policy)
- balancer API supports:
  - `GET /api/v1/balancers`
  - `POST /api/v1/balancers`
  - `GET /api/v1/balancers/{id}`
  - `PATCH /api/v1/balancers/{id}`
  - `DELETE /api/v1/balancers/{id}`
  - `POST /api/v1/balancers/{id}/pick` (test member selection on node)
- probe API supports:
  - `GET /api/v1/probes/results`
  - `POST /api/v1/probes/balancers/{id}/run` (records fresh ping/load probes for members)
- client-routing API supports:
  - `POST /api/v1/bootstrap`
  - `POST /api/v1/probe`
  - `POST /api/v1/best-ingress` (includes optional planned ingress->egress path)
  - `POST /api/v1/session-rebind`
- topology API supports:
  - `GET /api/v1/graph` (nodes + links + derived metrics for backend-driven topology graph)
  - `POST /api/v1/paths/plan` (shortest-path planning by latency/load/loss scoring)
- background services:
  - probe scheduler periodically refreshes node/link ping+load metrics into `probe_results`
- client-routing security:
  - bearer auth for `/bootstrap`, `/probe`, `/best-ingress`, `/session-rebind`
  - in-memory token bucket rate limits with `429 + Retry-After`
- admin/control-plane security:
  - bearer auth for admin/control-plane endpoints
  - static bearer tokens may carry explicit roles (`viewer=...`, `operator=...`, `admin=...`)
  - JWT admin roles are read from `role` / `roles` claims
  - DB-backed access rules API supports:
    - `GET /api/v1/access-rules`
    - `GET /api/v1/access-rules/matrix`
    - `PUT /api/v1/access-rules/{permission_key}`
    - `DELETE /api/v1/access-rules/{permission_key}`
