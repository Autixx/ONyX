# WGD_AWG_fix_multihop / ONX

This repository currently contains two parallel tracks:

1. `WGDashboard` fork with:
- `AmneziaWG 2.0` support
- multihop routing
- balancers
- DNS interception / local DNS routing
- GeoIP direct routing helpers

2. `ONX` backend-first control-plane prototype for a distributed overlay transport network:
- node registry
- SSH-based deployment flow
- AWG site-to-site link model
- jobs / retries / locks
- route policies
- DNS / Geo / balancer policy models
- client ingress selection protocol
- topology graph and weighted path planner

`WGDashboard` remains the legacy operational surface.

`ONX` is the new control-plane under active development.

## Status

Current repository state:

- legacy `WGDashboard` path is installable and usable on Ubuntu
- `ONX` backend is in alpha stage
- native ONX install/update flow exists
- native TLS setup for ONX exists
- post-install alpha smoke exists

Current ONX limitations:

- no finished UI
- no full production HA control-plane yet

## Repository Layout

Main areas:

- `src/` - legacy WGDashboard fork
- `scripts/` - installers, TLS helpers, smoke checks, auth rotation
- `onx/` - new ONX backend
- `docs/architecture/` - ONX design and architecture records

Important architecture docs:

- [ONX_TECHNICAL_DESIGN.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_TECHNICAL_DESIGN.md)
- [ONX_V0_2_BLUEPRINT.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_V0_2_BLUEPRINT.md)
- [ONX_CLIENT_PROTOCOL_V1.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_CLIENT_PROTOCOL_V1.md)
- [ONX_MIGRATIONS.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_MIGRATIONS.md)
- [ADR-0004-control-plane-ha.md](Q:\MyVeryOwnAwgStS\docs\architecture\ADR-0004-control-plane-ha.md)
- [ADR-0005-interface-runtime-isolation.md](Q:\MyVeryOwnAwgStS\docs\architecture\ADR-0005-interface-runtime-isolation.md)
- [ADR-0006-job-retry-and-cancel.md](Q:\MyVeryOwnAwgStS\docs\architecture\ADR-0006-job-retry-and-cancel.md)
- [ADR-0007-job-target-locking.md](Q:\MyVeryOwnAwgStS\docs\architecture\ADR-0007-job-target-locking.md)

## Legacy WGDashboard Install

Ubuntu 22.04 / 24.04:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/Autixx/WGD_AWG_fix_multihop.git
cd WGD_AWG_fix_multihop
sudo bash scripts/install_ubuntu.sh
```

What the installer can auto-install:

- `amneziawg-tools` (`awg`, `awg-quick`)
- `amneziawg-go`
- `nodejs` / `npm` for frontend build

Skip AWG / Node install if needed:

```bash
sudo bash scripts/install_ubuntu.sh \
  --no-install-awg \
  --no-install-node \
  --no-build-frontend
```

Bootstrap ready inbound in one command:

```bash
sudo bash scripts/install_ubuntu.sh --bootstrap-inbound awg0 --bootstrap-protocol awg
```

Enable HTTPS for WGDashboard:

```bash
sudo bash scripts/install_ubuntu.sh \
  --bootstrap-inbound awg0 \
  --bootstrap-protocol awg \
  --enable-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

Optional WGDashboard TLS flags:

- `--tls-domain <fqdn>`
- `--tls-cert-days <num>`
- `--tls-https-port <port>`
- `--tls-force`
- `--no-tls-local-bind`

AWG 2.0 bootstrap parameters supported:

- `Jc`
- `Jmin`
- `Jmax`
- `S1`
- `S2`
- `S3`
- `S4`
- `H1`
- `H2`
- `H3`
- `H4`

Legacy `I1..I5` are not used.

If explicit `--awg-*` values are not passed, installer generates them randomly.

Explicit AWG example:

```bash
sudo bash scripts/install_ubuntu.sh \
  --bootstrap-inbound awg0 \
  --bootstrap-protocol awg \
  --bootstrap-address 10.66.66.1/24 \
  --bootstrap-listen-port 51820 \
  --bootstrap-out-if ens3 \
  --awg-jc 4 --awg-jmin 40 --awg-jmax 70 \
  --awg-s1 20 --awg-s2 40 --awg-s3 80 --awg-s4 120 \
  --awg-h1 1 --awg-h2 2 --awg-h3 3 --awg-h4 4 \
  --bootstrap-force
```

Service checks:

```bash
systemctl status wg-dashboard.service --no-pager
journalctl -u wg-dashboard.service -f
```

## ONX Overview

`ONX` lives under `onx/` and is intended as a backend-first control-plane.

Implemented backend surface at this stage:

- health endpoints
- worker diagnostics
- jobs queue / retry / cancel / locks
- nodes CRUD
- node runtime bootstrap job
- links CRUD / validate / apply
- probes API
- route policies CRUD
- DNS policies CRUD
- geo policies CRUD
- balancers CRUD
- topology graph API
- weighted path planner
- client ingress protocol:
  - `/bootstrap`
  - `/probe`
  - `/best-ingress`
  - `/session-rebind`

## ONX Native Install

Ubuntu 22.04 / 24.04, no Docker:

```bash
cd /opt/wgd-awg-multihop
sudo bash scripts/install_onx_ubuntu.sh
```

Default install result:

- service: `onx-api.service`
- bind: `127.0.0.1:8081`
- env file: `/etc/onx/onx.env`
- auth info: `/etc/onx/client-auth.txt`
- admin auth info: `/etc/onx/admin-auth.txt`
- DB: local PostgreSQL (`onx`)
- client-routing auth mode: `token`
- admin/control-plane auth mode: `token`
- bearer token is auto-generated if not supplied

Useful overrides:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --ref dev \
  --bind-host 0.0.0.0 \
  --bind-port 8081 \
  --postgres-db onx \
  --postgres-user onx \
  --postgres-password 'strong-password'
```

Explicit client auth selection:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --client-auth-mode token_or_jwt \
  --client-api-tokens "token-a,token-b"
```

JWT mode at install:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --client-auth-mode jwt \
  --client-api-jwt-issuer onyx-control \
  --client-api-jwt-audience onyx-client
```

Separate admin auth selection:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --admin-auth-mode token_or_jwt \
  --admin-api-tokens "admin-token-a,admin-token-b"
```

## ONX Native TLS

Install ONX with nginx + self-signed HTTPS immediately:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --enable-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

Optional ONX TLS flags:

- `--tls-domain <fqdn>`
- `--tls-cert-days <num>`
- `--tls-https-port <port>`
- `--tls-force`
- `--no-tls-local-bind`

Enable HTTPS later on an existing ONX install:

```bash
sudo bash scripts/setup_onx_tls_openssl.sh \
  --ip <SERVER_PUBLIC_IP> \
  --upstream-host 127.0.0.1 \
  --upstream-port 8081
```

## ONX Alpha Smoke

Run smoke automatically right after install:

```bash
sudo bash scripts/install_onx_ubuntu.sh --run-alpha-smoke
```

Strict smoke example:

```bash
sudo bash scripts/install_onx_ubuntu.sh \
  --run-alpha-smoke \
  --smoke-expect-auth \
  --smoke-check-rate-limit
```

Manual smoke:

```bash
python scripts/onx_alpha_smoke.py --base-url http://127.0.0.1:8081/api/v1
```

Strict manual smoke:

```bash
python scripts/onx_alpha_smoke.py \
  --base-url http://127.0.0.1:8081/api/v1 \
  --client-bearer-token "$(sudo awk -F= '/^tokens=/{print $2}' /etc/onx/client-auth.txt | cut -d, -f1)" \
  --admin-bearer-token "$(sudo awk -F= '/^tokens=/{print $2}' /etc/onx/admin-auth.txt | cut -d, -f1)" \
  --expect-auth \
  --check-rate-limit
```

Current smoke covers:

- `/health`
- `/bootstrap`
- `/probe`
- `/best-ingress`
- `/graph`
- `/paths/plan`
- `/session-rebind`

Strict smoke additionally verifies:

- `401` + `WWW-Authenticate: Bearer`
- `429` + `Retry-After`

## ONX Update

Update ONX in place:

```bash
cd /opt/wgd-awg-multihop
sudo bash scripts/update_onx_ubuntu.sh --ref dev
```

Refresh TLS during update:

```bash
cd /opt/wgd-awg-multihop
sudo bash scripts/update_onx_ubuntu.sh \
  --ref dev \
  --refresh-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

## ONX Auth Rotation

Default generated auth data:

```bash
sudo cat /etc/onx/client-auth.txt
sudo cat /etc/onx/admin-auth.txt
```

Rotate client-routing auth without manual env edits:

```bash
sudo bash scripts/rotate_onx_auth.sh
```

Switch to JWT mode and rotate secret:

```bash
sudo bash scripts/rotate_onx_auth.sh \
  --client-auth-mode jwt \
  --client-api-jwt-issuer onyx-control \
  --client-api-jwt-audience onyx-client
```

Switch to token-or-jwt:

```bash
sudo bash scripts/rotate_onx_auth.sh \
  --client-auth-mode token_or_jwt
```

Rotate admin/control-plane auth:

```bash
sudo bash scripts/rotate_onx_admin_auth.sh
```

Switch admin auth to JWT mode:

```bash
sudo bash scripts/rotate_onx_admin_auth.sh \
  --admin-auth-mode jwt \
  --admin-api-jwt-issuer onyx-admin \
  --admin-api-jwt-audience onyx-admin-api
```

## ONX Service Checks

```bash
systemctl status onx-api.service --no-pager
journalctl -u onx-api.service -f
curl -fsS http://127.0.0.1:8081/api/v1/health
```

If HTTPS is enabled:

```bash
curl -kfsS https://<SERVER_PUBLIC_IP>/api/v1/health
```

## ONX Client-Routing Auth and Rate Limit

Current supported auth modes:

- `disabled`
- `token`
- `jwt`
- `token_or_jwt`

Current implementation scope:

- client auth and rate-limit are enforced for:
  - `/bootstrap`
  - `/probe`
  - `/best-ingress`
  - `/session-rebind`

- admin auth/ACL is enforced for:
  - `/health/worker`
  - `/jobs/*`
  - `/nodes/*`
  - `/links/*`
  - `/balancers/*`
  - `/route-policies/*`
  - `/dns-policies/*`
  - `/geo-policies/*`
  - `/probes/*`
  - `/graph`
  - `/paths/plan`

- public without auth:
  - `/health`

Environment examples:

```bash
# token mode
export ONX_CLIENT_API_AUTH_MODE=token
export ONX_CLIENT_API_TOKENS="token-one,token-two"

# admin token mode
export ONX_ADMIN_API_AUTH_MODE=token
export ONX_ADMIN_API_TOKENS="admin-token-one,admin-token-two"

# JWT mode (HS256)
export ONX_CLIENT_API_AUTH_MODE=jwt
export ONX_CLIENT_API_JWT_SECRET="change-me-long-random-secret"
export ONX_CLIENT_API_JWT_ISSUER="onyx-control"
export ONX_CLIENT_API_JWT_AUDIENCE="onyx-client"

# admin JWT mode (HS256)
export ONX_ADMIN_API_AUTH_MODE=jwt
export ONX_ADMIN_API_JWT_SECRET="change-me-long-random-admin-secret"
export ONX_ADMIN_API_JWT_ISSUER="onyx-admin"
export ONX_ADMIN_API_JWT_AUDIENCE="onyx-admin-api"

# rate limit
export ONX_CLIENT_RATE_LIMIT_ENABLED=true
export ONX_CLIENT_RL_BOOTSTRAP_IP_RATE_PER_MINUTE=10
export ONX_CLIENT_RL_PROBE_SESSION_RATE_PER_MINUTE=120
export ONX_CLIENT_RL_BEST_SESSION_RATE_PER_MINUTE=60
export ONX_CLIENT_RL_REBIND_SESSION_RATE_PER_MINUTE=20
```

When limited, endpoints return `429` with `Retry-After`.

ACL rules for admin JWT:

- read methods (`GET`, `HEAD`, `OPTIONS`) accept roles from `ONX_ADMIN_API_READ_ROLES`
- write methods (`POST`, `PUT`, `PATCH`, `DELETE`) accept roles from `ONX_ADMIN_API_WRITE_ROLES`
- static admin bearer tokens are treated as full `admin`
- JWT roles are read from `roles` or `role` claim

## GeoIP Direct in Legacy Multihop

Legacy multihop backend supports GeoIP direct routing via `ipset`.

Relevant fields:

- `GeoDirectEnabled`
- `GeoDirectCountries`
- `GeoDirectSourceTemplate`

Default source template:

- `https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone`

Behavior:

- selected country CIDRs are loaded into `ipset`
- traffic to them stays on the main route
- the rest follows multihop policy route

## Branching Note

Current active ONX work is happening in `dev`.

If you want the latest ONX alpha changes:

```bash
git checkout dev
git pull --ff-only origin dev
```
