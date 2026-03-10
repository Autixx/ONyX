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
  - `PATCH /api/v1/route-policies/{id}`
  - `DELETE /api/v1/route-policies/{id}`
  - `POST /api/v1/route-policies/{id}/apply` (enqueues policy apply job)
- dns policy API supports:
  - `GET /api/v1/dns-policies`
  - `POST /api/v1/dns-policies`
  - `GET /api/v1/dns-policies/{id}`
  - `PATCH /api/v1/dns-policies/{id}`
  - `DELETE /api/v1/dns-policies/{id}`
  - `POST /api/v1/dns-policies/{id}/apply` (enqueues apply for parent route policy)
