Thats my fork for WGDashboard with couple of features - AWG2.0 support, easy-to-route connection destination (such 3x-ui has) and multihop with balancers support.
Original project: [https://wg.wgdashboard.dev/](https://wg.wgdashboard.dev/)

## Ubuntu 22.04 / 24.04 installer

Run on a clean VPS:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/Autixx/WGD_AWG_fix_multihop.git
cd WGD_AWG_fix_multihop
sudo bash scripts/install_ubuntu.sh
```

Installer now auto-installs missing AWG components from official repos:
- `amneziawg-tools` (`awg`, `awg-quick`)
- `amneziawg-go`
- Node.js/npm (for frontend build)

If you want to skip that behavior, use:

```bash
sudo bash scripts/install_ubuntu.sh --no-install-awg --no-install-node --no-build-frontend
```

One-command deploy with ready inbound `wg0` (keys + NAT + interface up):

```bash
sudo bash scripts/install_ubuntu.sh --bootstrap-inbound wg0
```

Enable HTTPS (OpenSSL self-signed cert + nginx reverse proxy):

```bash
sudo bash scripts/install_ubuntu.sh \
  --bootstrap-inbound awg0 \
  --bootstrap-protocol awg \
  --enable-tls-openssl \
  --tls-ip <SERVER_PUBLIC_IP>
```

Optional TLS flags:
- `--tls-domain <fqdn>`: put DNS SAN/CN into cert
- `--tls-cert-days <num>`: cert validity
- `--tls-https-port <port>`: nginx HTTPS port (default `443`)
- `--tls-force`: regenerate cert files
- `--no-tls-local-bind`: keep panel on public `app_ip` instead of `127.0.0.1`

Example for AWG inbound:

```bash
sudo bash scripts/install_ubuntu.sh --bootstrap-inbound awg0 --bootstrap-protocol awg --bootstrap-listen-port 51820
```

Custom AWG sources/refs are supported:

```bash
sudo bash scripts/install_ubuntu.sh \
  --awg-tools-repo https://github.com/amnezia-vpn/amneziawg-tools.git \
  --awg-tools-ref master \
  --awg-go-repo https://github.com/amnezia-vpn/amneziawg-go.git \
  --awg-go-ref master
```

AWG 2.0 bootstrap fields are supported (without legacy `I1..I5`).  
Supported keys: `Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `S3`, `S4`, `H1`, `H2`, `H3`, `H4`.
If you do not pass `--awg-*` values, they are randomly generated for each new interface.

Example with explicit AWG 2.0 values:

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

After install:

```bash
systemctl status wg-dashboard.service --no-pager
journalctl -u wg-dashboard.service -f
```

## ONX native install (no Docker)

Install ONX API + PostgreSQL + systemd service on Ubuntu 22.04/24.04:

```bash
cd /opt/wgd-awg-multihop
sudo bash scripts/install_onx_ubuntu.sh
```

Defaults:
- service: `onx-api.service`
- bind: `127.0.0.1:8081`
- env: `/etc/onx/onx.env`
- DB: local PostgreSQL (`onx` / `onx`)

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

Update ONX in-place:

```bash
cd /opt/wgd-awg-multihop
sudo bash scripts/update_onx_ubuntu.sh --ref dev
```

Service checks:

```bash
systemctl status onx-api.service --no-pager
journalctl -u onx-api.service -f
curl -fsS http://127.0.0.1:8081/api/v1/health
```

## ONX alpha smoke check

After ONX API is running, you can validate the minimal ingress protocol end-to-end:

```bash
python scripts/onx_alpha_smoke.py --base-url http://127.0.0.1:8081/api/v1
```

This checks:
- `/health`
- `/bootstrap`
- `/probe`
- `/best-ingress`
- `/session-rebind`

## ONX client-routing auth and rate-limit (env)

Examples:

```bash
# Auth mode: token | jwt | token_or_jwt | disabled
export ONX_CLIENT_API_AUTH_MODE=token
export ONX_CLIENT_API_TOKENS="token-one,token-two"

# Or JWT (HS256)
export ONX_CLIENT_API_AUTH_MODE=jwt
export ONX_CLIENT_API_JWT_SECRET="change-me-long-random-secret"
export ONX_CLIENT_API_JWT_ISSUER="onyx-control"
export ONX_CLIENT_API_JWT_AUDIENCE="onyx-client"

# Rate limit
export ONX_CLIENT_RATE_LIMIT_ENABLED=true
export ONX_CLIENT_RL_BOOTSTRAP_IP_RATE_PER_MINUTE=10
export ONX_CLIENT_RL_PROBE_SESSION_RATE_PER_MINUTE=120
export ONX_CLIENT_RL_BEST_SESSION_RATE_PER_MINUTE=60
export ONX_CLIENT_RL_REBIND_SESSION_RATE_PER_MINUTE=20
```

When limited, endpoints return `429` with `Retry-After`.

## MultiHop GeoIP Direct (backend)

MultiHop supports GeoIP direct routing via `ipset`:
- `GeoDirectEnabled`: enable/disable GeoIP direct mode
- `GeoDirectCountries`: comma-separated ISO country codes (example: `ru,kz`)
- `GeoDirectSourceTemplate`: URL template with `{country}` placeholder  
  default: `https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone`

When enabled, destination CIDRs for selected countries are loaded into `ipset` and traffic to them is kept on the main route (direct), while the rest follows MultiHop routing.
