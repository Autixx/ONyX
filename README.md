# ONyX

ONyX is a backend-first control-plane for a distributed overlay transport network.

Current alpha surface:

- node registry
- SSH-based node onboarding
- remote AWG prerequisite installation
- AWG site-to-site link model
- jobs / retries / locks
- route policies
- DNS / Geo / balancer policy models
- client ingress selection protocol
- topology graph and weighted path planner
- admin TUI (`onx`)
- native Ubuntu install / update flow
- native TLS setup
- browser login/session auth
- admin websocket event stream
- same-origin static UI hosting scaffold
- post-install alpha smoke

## Repository Layout

- `onx/` - ONyX backend
- `scripts/` - installers, admin TUI, smoke, auth rotation, TLS helpers
- `docs/architecture/` - design docs and roadmap

Important docs:

- [ONX_TECHNICAL_DESIGN.md](Q:\ONyX_export\docs\architecture\ONX_TECHNICAL_DESIGN.md)
- [ONX_V0_2_BLUEPRINT.md](Q:\ONyX_export\docs\architecture\ONX_V0_2_BLUEPRINT.md)
- [ONX_CLIENT_PROTOCOL_V1.md](Q:\ONyX_export\docs\architecture\ONX_CLIENT_PROTOCOL_V1.md)
- [ONX_WEB_UI_HANDOFF.md](Q:\ONyX_export\docs\architecture\ONX_WEB_UI_HANDOFF.md)
- [ONX_CLIENT_DELIVERY_ARCHITECTURE.md](Q:\ONyX_export\docs\architecture\ONX_CLIENT_DELIVERY_ARCHITECTURE.md)
- [ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md](Q:\ONyX_export\docs\architecture\ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md)
- [ONX_SUBSCRIPTIONS_AND_BILLING.md](Q:\ONyX_export\docs\architecture\ONX_SUBSCRIPTIONS_AND_BILLING.md)
- [ONX_V0_3_ROADMAP.md](Q:\ONyX_export\docs\architecture\ONX_V0_3_ROADMAP.md)
- [ONX_MIGRATIONS.md](Q:\ONyX_export\docs\architecture\ONX_MIGRATIONS.md)
- [ALPHA_ACCEPTANCE_CHECKLIST.md](Q:\ONyX_export\docs\architecture\ALPHA_ACCEPTANCE_CHECKLIST.md)

## Status

Current state:

- backend-first alpha
- no finished UI yet
- admin/control-plane API is usable
- install/update/smoke path is usable on Ubuntu 22.04/24.04
- managed Ubuntu nodes can be onboarded and prepared for AWG s2s from control-plane

## Native Install

Ubuntu 22.04 / 24.04, no Docker:

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/Autixx/ONyX.git /opt/onyx
cd /opt/onyx
sudo git checkout main
sudo bash scripts/install_onx_ubuntu.sh
```

Default install result:

- service: `onx-api.service`
- bind: `127.0.0.1:8081`
- env file: `/etc/onx/onx.env`
- client auth info: `/etc/onx/client-auth.txt`
- admin auth info: `/etc/onx/admin-auth.txt`
- admin web auth info: `/etc/onx/admin-web-auth.txt`
- DB: local PostgreSQL (`onx`)
- install dir: `/opt/onyx`

Web UI foundation now present on backend:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`
- `WS /api/v1/ws/admin/events`
- static UI mount from `/opt/onyx/apps/web-admin/dist` when build exists

Useful overrides:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --ref main \
  --bind-host 0.0.0.0 \
  --bind-port 8081 \
  --postgres-db onx \
  --postgres-user onx \
  --postgres-password 'strong-password'
```

## Native TLS

Install with nginx + self-signed HTTPS:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --enable-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

Enable HTTPS later on an existing install:

```bash
sudo bash scripts/setup_onx_tls_openssl.sh \
  --ip <SERVER_PUBLIC_IP> \
  --upstream-host 127.0.0.1 \
  --upstream-port 8081
```

Because ONyX is deployed same-origin behind nginx, browser auth cookies and websocket
connections work over the same HTTPS origin.

## Alpha Smoke

Run smoke automatically right after install:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --run-alpha-smoke \
  --smoke-expect-auth \
  --smoke-check-rate-limit
```

Manual strict smoke:

```bash
python scripts/onx_alpha_smoke.py \
  --base-url http://127.0.0.1:8081/api/v1 \
  --client-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/client-auth.txt)" \
  --admin-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
  --expect-auth \
  --check-rate-limit
```

## Admin TUI

Interactive local helper:

```bash
onx
```

Main sections:

- `System`
- `Nodes`
- `Links`
- `Policies`
- `Jobs`
- `Audit / Access`
- `Topology`
- `API Debug`

Node actions include:

- create / provision / list / edit / delete
- availability check
- runtime bootstrap
- capabilities view
- AWG readiness check

`bootstrap-runtime` on Ubuntu managed nodes now also auto-installs:

- `awg`
- `awg-quick`
- `amneziawg-go`
- `iptables`
- `ipset`
- `resolvconf`
- Go toolchain if needed for `amneziawg-go`

Remote SSH user for that step must be:

- `root`, or
- a user with passwordless `sudo`

## Update

Update in place:

```bash
cd /opt/onyx
sudo bash scripts/update_onx_ubuntu.sh --ref main
```

Refresh TLS during update:

```bash
cd /opt/onyx
sudo bash scripts/update_onx_ubuntu.sh \
  --ref main \
  --refresh-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

## Service Checks

```bash
systemctl status onx-api.service --no-pager
journalctl -u onx-api.service -f
curl -fsS http://127.0.0.1:8081/api/v1/health
```

## Web UI Backend Contract

Admin browser login:

```bash
curl -k -X POST https://<HOST>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<PASSWORD_FROM_/etc/onx/admin-web-auth.txt>"}'
```

Current session:

```bash
curl -k https://<HOST>/api/v1/auth/me
```

Admin realtime stream:

- websocket endpoint: `/api/v1/ws/admin/events`
- same-origin browser auth uses secure session cookie
- event types currently emitted:
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

## Branching Note

This repository is ONyX-only.

Primary branch:

- `main`
