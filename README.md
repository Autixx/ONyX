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
- retention cleanup scheduler exists
- control-plane state export/import exists

Current ONX limitations:

- no finished UI
- no full production HA control-plane yet
- still needs one clean Ubuntu end-to-end validation before being called install-safe

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
- [ONX_CLIENT_DELIVERY_ARCHITECTURE.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_CLIENT_DELIVERY_ARCHITECTURE.md)
- [ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md)
- [ONX_SUBSCRIPTIONS_AND_BILLING.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_SUBSCRIPTIONS_AND_BILLING.md)
- [ONX_V0_3_ROADMAP.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_V0_3_ROADMAP.md)
- [ONX_MIGRATIONS.md](Q:\MyVeryOwnAwgStS\docs\architecture\ONX_MIGRATIONS.md)
- [ALPHA_ACCEPTANCE_CHECKLIST.md](Q:\MyVeryOwnAwgStS\docs\architecture\ALPHA_ACCEPTANCE_CHECKLIST.md)
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
- access rules CRUD
- jobs queue / retry / cancel / locks
- audit logs API
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
- retention policy API and cleanup
- client ingress protocol:
  - `/bootstrap`
  - `/probe`
  - `/best-ingress`
  - `/session-rebind`

## ONX Node Admin CLI

Interactive local helper for node onboarding:

Unified terminal menu after install:

```bash
onx
```

Menu actions:

- `System`:
  - daemon status
  - worker health
  - retention policy / cleanup
  - probe results
  - daemon restart
  - alpha smoke test
- `Nodes`:
  - create / provision / list / edit / delete by name
  - availability check
  - runtime bootstrap
  - capability view
- `Links`:
  - list / view / create / validate / apply
- `Policies`:
  - route policies
  - DNS policies
  - geo policies
  - balancers
- `Jobs`:
  - list
  - last result
  - events
  - cancel / retry-now / force-cancel
- `Audit / Access`:
  - audit logs
  - access rules
  - access rule matrix
- `Topology`:
  - graph summary
  - path planning
- `API Debug`:
  - raw GET / POST / PATCH / PUT / DELETE with admin or client token

```bash
python scripts/onx_nodes.py list-nodes
python scripts/onx_nodes.py add-node
python scripts/onx_nodes.py edit-node <NODE_ID_OR_NAME>
python scripts/onx_nodes.py provision-node
python scripts/onx_nodes.py delete-node <NODE_ID_OR_NAME>
```

It will prompt for:

- node name
- role
- management address
- SSH host / port / user
- auth mode (`password` or `private_key`)
- password or private key file

Then it will:

1. create the node in ONX
2. store the SSH secret

`provision-node` does the same, then also:

3. runs `discover`
4. runs `bootstrap-runtime`

Run discovery for an existing node:

```bash
python scripts/onx_nodes.py discover <NODE_ID_OR_NAME>
python scripts/onx_nodes.py bootstrap-runtime <NODE_ID_OR_NAME>
python scripts/onx_nodes.py delete-node <NODE_ID_OR_NAME>
```

By default both commands wait for the job to finish and print capabilities.

Useful overrides:

```bash
python scripts/onx_nodes.py --base-url http://127.0.0.1:8081/api/v1 add-node
python scripts/onx_nodes.py --admin-token "<ADMIN_TOKEN>" discover node-msk-1
python scripts/onx_nodes.py discover node-msk-1 --no-wait
python scripts/onx_nodes.py bootstrap-runtime node-msk-1 --no-wait
python scripts/onx_nodes.py list-nodes
python scripts/onx_nodes.py delete-node node-msk-1 -y
```

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
  --admin-api-tokens "viewer=admin-view-token,operator=admin-op-token,admin=admin-root-token"
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
  --client-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/client-auth.txt)" \
  --admin-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
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
  - `/audit-logs`
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
- plain static admin tokens are treated as full `admin`
- role-mapped static admin tokens use roles from the token entry itself
- JWT roles are read from `roles` or `role` claim

Static admin token format:

- backward-compatible plain token: `supersecrettoken`
- explicit role mapping: `viewer=token1,operator=token2,admin=token3`
- multi-role token: `viewer|operator=token4`

## ONX Access Rules

API access permissions can now be overridden from the database.

Use cases:

- give `viewer` read-only access to topology and jobs
- allow `operator` to apply links and policies
- keep `admin`-only access to ACL management itself
- override a specific API action without changing code or env

Endpoints:

- `GET /api/v1/access-rules`
- `GET /api/v1/access-rules/matrix`
- `PUT /api/v1/access-rules/{permission_key}`
- `DELETE /api/v1/access-rules/{permission_key}`

Examples of permission keys:

- `audit_logs.read`
- `maintenance.read`
- `maintenance.write`
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

ACL matrix helper commands:

```bash
# export effective matrix
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env export --output acl-effective.json

# export built-in defaults only
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env export-defaults --output acl-defaults.json

# import overrides
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env import --input acl-effective.json

# replace current DB overrides with file contents
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env import --input acl-effective.json --replace
```

## ONX Audit Logs

Audit events are stored in `event_logs`.

Currently audited:

- access-rule upsert
- access-rule delete
- client auth rotation
- admin auth rotation
- ACL matrix import

Read the latest audit entries:

```bash
curl -H "Authorization: Bearer $(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
  "http://127.0.0.1:8081/api/v1/audit-logs?limit=50"
```

Useful filters:

- `entity_type=access_rule`
- `entity_type=auth_rotation`
- `entity_id=client`
- `level=info`

## ONX Retention

Runtime cleanup is built in:

- `probe_results` are cleaned by retention policy
- `event_logs` are cleaned by retention policy
- cleanup runs in the background scheduler
- cleanup can also be triggered manually

Defaults:

- `ONX_RETENTION_SCHEDULER_ENABLED=true`
- `ONX_RETENTION_SCHEDULER_INTERVAL_SECONDS=3600`
- `ONX_PROBE_RESULT_RETENTION_SECONDS=604800`
- `ONX_EVENT_LOG_RETENTION_SECONDS=2592000`

Manual policy check:

```bash
curl -H "Authorization: Bearer $(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
  http://127.0.0.1:8081/api/v1/maintenance/retention
```

Manual cleanup run:

```bash
curl -X POST \
  -H "Authorization: Bearer $(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
  http://127.0.0.1:8081/api/v1/maintenance/cleanup
```

## ONX Control-Plane State

Separate from ACL matrix, ONX can export/import the main control-plane objects:

- nodes
- links
- balancers
- route policies
- dns policies
- geo policies

By default, export does not include secrets.

Export:

```bash
python scripts/onx_control_plane_state.py --env-file /etc/onx/onx.env export --output onx-state.json
```

Export with active node management secrets in plaintext:

```bash
python scripts/onx_control_plane_state.py --env-file /etc/onx/onx.env export --output onx-state-with-secrets.json --include-secrets
```

Import:

```bash
python scripts/onx_control_plane_state.py --env-file /etc/onx/onx.env import --input onx-state.json
```

Replace current control-plane state with file contents:

```bash
python scripts/onx_control_plane_state.py --env-file /etc/onx/onx.env import --input onx-state.json --replace
```

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
