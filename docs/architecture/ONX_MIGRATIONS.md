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
- jobs API supports:
  - `POST /api/v1/jobs/{id}/cancel`
  - `POST /api/v1/jobs/{id}/retry-now`
  - `POST /api/v1/jobs/{id}/force-cancel` (only for expired-lease running jobs)
