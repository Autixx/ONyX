# ONX Alpha Acceptance Checklist

## Purpose

This checklist is the minimum acceptance path for the first clean-server ONX alpha deployment on Ubuntu 22.04.

It is not a full operations manual.

It is a strict go/no-go list for:

- install validity
- auth validity
- API surface reachability
- basic control-plane persistence
- first backup/restore path

## Environment

Recommended minimum for first alpha validation:

- Ubuntu 22.04 LTS
- 2 vCPU
- 2 GB RAM
- 1-2 GB swap
- public IPv4

Recommended test assumptions:

- clean server
- no existing PostgreSQL customization
- no existing ONX config under `/etc/onx`
- no existing service named `onx-api`

## 1. Base OS Preparation

Run:

```bash
sudo apt-get update && sudo apt-get install -y git curl
```

Optional but recommended on 2 GB RAM:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Acceptance:

- `swapon --show` lists `/swapfile`
- `free -h` shows swap

## 2. Repository Fetch

Run:

```bash
sudo git clone https://github.com/Autixx/ONyX.git /opt/onyx
cd /opt/onyx
sudo git checkout main
```

Acceptance:

- repo exists under `/opt/onyx`
- branch is `main`

## 3. Native Install

Run:

```bash
cd /opt/onyx
sudo bash scripts/install_onx_ubuntu.sh --run-alpha-smoke --smoke-expect-auth --smoke-check-rate-limit
```

Acceptance:

- installer finishes without shell error
- `onx-api.service` exists
- PostgreSQL is installed and running
- smoke finishes successfully

## 4. Service Health

Run:

```bash
systemctl status onx-api.service --no-pager
curl -fsS http://127.0.0.1:8081/api/v1/health
```

Acceptance:

- systemd service state is `active (running)`
- health endpoint returns `status=ok`

If failed:

```bash
journalctl -u onx-api.service -n 200 --no-pager
```

## 5. Auth Artifacts

Run:

```bash
sudo cat /etc/onx/client-auth.txt
sudo cat /etc/onx/admin-auth.txt
```

Acceptance:

- both files exist
- both contain `mode=...`
- token mode contains `primary_token=...`

## 6. Strict Smoke Re-Run

Run:

```bash
python /opt/onyx/scripts/onx_alpha_smoke.py \
  --base-url http://127.0.0.1:8081/api/v1 \
  --client-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/client-auth.txt)" \
  --admin-bearer-token "$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)" \
  --expect-auth \
  --check-rate-limit
```

Acceptance:

- smoke exits `0`
- auth checks pass
- rate-limit checks pass

## 7. Maintenance and Audit

Run:

```bash
ADMIN_TOKEN="$(sudo awk -F= '/^primary_token=/{print $2}' /etc/onx/admin-auth.txt)"
curl -fsS -H "Authorization: Bearer ${ADMIN_TOKEN}" http://127.0.0.1:8081/api/v1/maintenance/retention
curl -fsS -X POST -H "Authorization: Bearer ${ADMIN_TOKEN}" http://127.0.0.1:8081/api/v1/maintenance/cleanup
curl -fsS -H "Authorization: Bearer ${ADMIN_TOKEN}" "http://127.0.0.1:8081/api/v1/audit-logs?limit=20"
```

Acceptance:

- maintenance policy returns retention values
- manual cleanup returns structured counters
- audit log contains maintenance and auth-related records

## 8. ACL Export/Import

Run:

```bash
cd /opt/onyx
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env export --output /tmp/onx-acl.json
python scripts/onx_acl_matrix.py --env-file /etc/onx/onx.env import --input /tmp/onx-acl.json
```

Acceptance:

- export file is created
- import returns `status=ok`
- audit log contains `acl_matrix` import event

## 9. Control-Plane State Export

Run:

```bash
cd /opt/onyx
python scripts/onx_control_plane_state.py --env-file /etc/onx/onx.env export --output /tmp/onx-state.json
```

Acceptance:

- export file is created
- JSON is readable
- export contains top-level sections:
  - `nodes`
  - `links`
  - `balancers`
  - `route_policies`
  - `dns_policies`
  - `geo_policies`

## 10. Restart Safety

Run:

```bash
sudo systemctl restart onx-api.service
sleep 2
curl -fsS http://127.0.0.1:8081/api/v1/health
```

Acceptance:

- service comes back after restart
- health is still reachable

## 11. Update Path

Run:

```bash
cd /opt/onyx
sudo bash scripts/update_onx_ubuntu.sh --ref main
```

Acceptance:

- update finishes without migration/import errors
- service remains healthy

## 12. Go / No-Go Rule

Go for alpha usage if all of the following are true:

- install completed
- strict smoke passed
- auth files exist and are usable
- maintenance endpoints work
- audit log API works
- ACL export/import works
- control-plane state export works
- restart succeeds
- update succeeds

No-go if any of the following happen:

- install requires manual code edits
- smoke fails on a clean server
- service does not survive restart
- exported state is malformed
- auth files are missing or empty
- manual cleanup crashes

## First Optional Next Test

After this checklist passes, the next real acceptance step should be:

1. create two nodes
2. import management secrets
3. create one AWG link
4. apply link
5. verify handshake
6. create one route policy
7. export control-plane state
8. restore it on a second test instance
