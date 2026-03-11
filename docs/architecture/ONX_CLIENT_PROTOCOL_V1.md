# ONX Client Protocol v1

This file defines the minimal control protocol for ingress selection from client apps.

## Scope

Endpoints (under `/api/v1`):

- `POST /bootstrap`
- `POST /probe`
- `POST /best-ingress`
- `POST /session-rebind`

The protocol is control-plane only. It does not carry user traffic.

## 1) Bootstrap

`POST /api/v1/bootstrap`

Request:

- `device_id` (required)
- `client_public_ip` (optional)
- `client_country_code` (optional)
- `destination_country_code` (optional)
- `candidate_limit` (optional, default `6`)
- `metadata` (optional object)

Response:

- `session_id`
- `session_token`
- `expires_at`
- `probe_targets[]`:
  - `node_id`
  - `node_name`
  - `role`
  - `endpoint`
  - `status`
- `probe_interval_seconds`
- `probe_fresh_seconds`

## 2) Probe

`POST /api/v1/probe`

Request:

- `session_id`
- `session_token`
- `client_country_code` (optional)
- `destination_country_code` (optional)
- `measurements[]` (1..64):
  - `node_id`
  - `rtt_ms` (optional)
  - `jitter_ms` (optional)
  - `loss_pct` (optional, `0..100`)
  - `handshake_ms` (optional)
  - `throughput_mbps` (optional)
  - `raw` (optional object, client-native telemetry)

Response:

- `accepted`
- `rejected`
- `recorded_at`

## 3) Best Ingress

`POST /api/v1/best-ingress`

Request:

- `session_id`
- `session_token`
- `destination_country_code` (optional)
- `target_egress_node_id` (optional explicit egress)
- `require_fresh_probe` (default `true`)
- `max_candidates` (default `5`)
- `plan_path` (default `true`)
- `path_max_hops` (default `8`)
- `path_require_active_links` (default `true`)
- `path_latency_weight` (default `1.0`)
- `path_load_weight` (default `1.2`)
- `path_loss_weight` (default `1.5`)

Response:

- `selected`: chosen ingress
- `alternatives[]`: ranked backups
- `planned_path`: planned ingress->...->egress route (or planner error payload)
- `sticky_kept`: whether current ingress was kept due to hysteresis
- `reason`: `initial-bind | best-score | sticky-hysteresis | fallback-no-fresh-probe`
- `probe_window_seconds`
- `generated_at`

## 4) Session Rebind

`POST /api/v1/session-rebind`

Request:

- `session_id`
- `session_token`
- `target_node_id` (optional; if empty, auto-rebind via best-ingress logic)
- `force` (default `false`)

Response:

- `session_id`
- `previous_node_id`
- `current_node_id`
- `rebound_at`
- `reason`

## Scoring Model (v1)

Each probe sample is normalized into one score:

`score = rtt + jitter*0.7 + loss*12 + handshake*0.15 + control_load*40 + status_penalty - throughput_bonus`

Where:

- `control_load` comes from latest control-plane interface-load probe (`0..1`)
- `status_penalty`: reachable `0`, degraded `30`, unknown `60`, offline `2500`
- `throughput_bonus = min(throughput_mbps, 500) * 0.02`

Lower score is better.

If no fresh client probe exists for a candidate, fallback score is used from node status and control-load.

## Session Behavior

- Session TTL is sliding (extended on `/probe`, `/best-ingress`, `/session-rebind`).
- Expired sessions are deleted lazily.
- Old probe rows are purged by retention window.
