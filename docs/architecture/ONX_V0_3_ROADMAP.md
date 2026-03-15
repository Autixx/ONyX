# ONX v0.3 Roadmap

## Status

Draft v0.1

## Purpose

This document translates the current ONX architecture into a practical next-step roadmap.

The goal is to keep future work ordered and legible:

- stabilize the current backend alpha
- add user/device/subscription access control
- introduce encrypted bundle delivery
- start the client application without losing architectural clarity

This is a sequencing document.

It is not a replacement for the technical design documents.

## Current Baseline

As of the current alpha, ONX already has:

- backend API
- native Ubuntu install/update flow
- PostgreSQL-backed control-plane
- jobs / locks / retries
- AWG link model and apply flow
- route policies
- DNS policies
- geo policies
- balancers
- topology graph and path planning
- client-routing endpoints
- admin/client auth
- DB-backed access rules
- audit logs
- retention cleanup
- ACL export/import
- control-plane state export/import

The next work must not destabilize this baseline.

## Next Backend Track: XRAY Transit Automation

The next transport-control-plane track should be the automation of the already proven manual path:

```text
CLIENT <-> XRAY ingress
       <-> XRAY daemon on GATE
       <-> dokodemo-door + TPROXY
       <-> kernel policy routing / fwmark
       <-> AWG site-to-site
       <-> remote egress node
       <-> Internet
```

This is not a new standalone transport.

It is a control-plane automation layer that binds:

- ingress services
- kernel routing policy
- inter-node transport
- remote egress

### Why This Comes Next

- the packet path has already been validated manually
- ONX already contains the needed bricks:
  - `XRAY services`
  - `AWG links/services`
  - `route policies`
  - `fwmark` and route-table application
- the missing part is automation glue, not basic transport capability

### Concrete Deliverables

1. `TransitPolicy` model and API
- one ingress service bound to one next-hop transport target
- first supported pair:
  - `XRAY ingress -> AWG link`

2. managed `TPROXY` runtime layer
- node-side runtime rendering and apply
- `iptables mangle`
- `TPROXY`
- `ip rule`
- `ip route add local`
- rollback and delete paths

3. `XRAY transit mode`
- separate from current access-service mode
- renders `dokodemo-door` + outbound mapping
- keeps `VLESS + xHTTP` ingress intact

4. health / reconcile
- detect drift after ingress, route-policy, or AWG changes
- expose degraded state if next hop becomes invalid

5. admin UI
- create transit policy
- select ingress service
- select next hop
- apply
- inspect state / health / last error

### Strict Scope Boundary

Do not expand this first track into:

- general multi-hop graph programming
- OpenVPN transit
- arbitrary Xray routing editor
- per-user transit overrides
- mixed failover matrix on day one

The first target is intentionally narrow:

- `XRAY ingress`
- `TPROXY transit capture`
- `AWG next hop`
- remote default egress

## Main Rule for v0.3

Do not jump straight into payments or a heavy GUI client.

The correct order is:

1. stabilize alpha deploy
2. add identity and entitlement layer
3. add encrypted bundle issuance
4. build client MVP against that contract
5. add commercial billing integrations later

## Recommended Repository Strategy

### Recommendation

Yes, the client application should start in the same repository.

Recommended reason:

- shared architecture and protocol evolve together
- easier coordination between backend and client delivery format
- easier version-locking during alpha
- fewer moving parts while protocol is still unstable

### Recommended Layout

Suggested monorepo growth:

```text
/onx
  backend control-plane

/apps
  /client-desktop
  /client-mobile    (later, optional)

/libs
  /profile-envelope
  /client-protocol
  /crypto-utils
```

### When to Split Later

Only split the client into a separate repo if at least one of the following becomes true:

- client release cadence diverges strongly from backend
- separate team ownership appears
- mobile/desktop codebase becomes operationally independent
- protocol format becomes stable enough to freeze interfaces

For now, monorepo is the correct choice.

## v0.3 Workstreams

The roadmap is split into six workstreams.

### Workstream A: Alpha Stabilization

Goal:

- confirm current ONX alpha on a clean Ubuntu VPS

Deliverables:

- one successful run of `ALPHA_ACCEPTANCE_CHECKLIST.md`
- bugfix pass from first clean-server findings
- freeze a known-good alpha install command

Exit condition:

- ONX installs cleanly on Ubuntu 22.04 without manual code edits

### Workstream B: Identity Foundation

Goal:

- introduce the minimum account and device model

Deliverables:

- `users`
- `plans`
- `subscriptions`
- `devices`
- configurable `device_limit`
- active/revoked/suspended states

Dependencies:

- none beyond current alpha baseline

Exit condition:

- ONX can decide whether a given user/device pair is allowed to receive service

### Workstream C: Entitlement and Bundle Issuance

Goal:

- replace reusable config delivery with short-lived encrypted bundles

Deliverables:

- device registration
- device keypair challenge-response
- entitlement evaluation service
- encrypted session bundle envelope
- bundle issue endpoint
- bundle re-issue / rebind endpoint

Dependencies:

- Workstream B

Exit condition:

- ONX can issue a device-bound bundle only to a valid user/subscription/device tuple

### Workstream D: Client MVP

Goal:

- create the first usable application that can consume ONX-issued bundles

Recommended scope for MVP:

- desktop first
- login
- device registration
- challenge-response
- fetch bundle
- establish first transport
- reconnect/failover between transport candidates

Non-goals for MVP:

- polished UI
- full billing cabinet
- advanced multi-platform sync
- every protocol at once

Recommended first transport support:

- `awg`
- optionally one fallback protocol after that

Dependencies:

- Workstream C

Exit condition:

- one desktop client can authenticate, register device, receive bundle, and establish tunnel

### Workstream E: Subscription Operations

Goal:

- make subscriptions operational without payment automation

Deliverables:

- create user
- assign plan
- set expiration
- set lifetime
- set device limit
- suspend / unsuspend
- revoke device

Dependencies:

- Workstream B

Exit condition:

- operator can fully manage access manually

### Workstream F: Commercial Billing Integration

Goal:

- attach commercial payment events to the entitlement layer

Deliverables:

- provider adapters later
- payment event ingestion
- subscription activation/extension from provider events
- audit trail for billing actions

Dependencies:

- Workstream E

Exit condition:

- payment events can change subscription state without touching transport core

## Recommended Development Order

The practical order should be:

### Phase 1

- finish alpha stabilization
- do not add major new runtime behavior before one clean-server validation

### Phase 2

- implement `users`
- implement `plans`
- implement `subscriptions`
- implement `devices`
- implement entitlement evaluation

### Phase 3

- implement device registration flow
- implement challenge-response
- implement short-lived encrypted profile bundle
- implement bundle issuance policy

### Phase 4

- start `apps/client-desktop`
- implement login + registration + bundle retrieval
- implement first transport runtime

### Phase 5

- operator CRUD for subscriptions/devices
- device replacement flow
- revoke / suspend / restore

### Phase 6

- payment integrations
- quota and usage accounting
- reseller flows if needed

## Concrete v0.3 Backend Deliverables

### New Tables

Minimum likely additions:

- `users`
- `plans`
- `subscriptions`
- `devices`
- `device_attestations` or equivalent metadata table
- `issued_bundles` or `bundle_events`

Optional later:

- `usage_counters`
- `payment_events`
- `invoices`

### New API Groups

Minimum likely additions:

- `/api/v1/users`
- `/api/v1/plans`
- `/api/v1/subscriptions`
- `/api/v1/devices`
- `/api/v1/bundles`

### New Services

Minimum likely additions:

- `user_service`
- `plan_service`
- `subscription_service`
- `device_service`
- `entitlement_service`
- `bundle_service`

## Concrete Client Deliverables

### Desktop MVP

Recommended first responsibilities:

- secure storage of device private key
- login to ONX
- device registration
- challenge signing
- bundle fetch
- local decryption
- runtime handoff into tunnel engine
- reconnect and fallback

### What the Client Must Not Need

The client must not require:

- full node topology
- full mesh inventory
- server-side balancer definitions
- operator route policy internals

The client should receive only:

- a small set of ingress candidates
- transport candidates
- bundle TTL
- opaque routing token

## Cross-Cutting Constraints

These must remain true throughout v0.3:

- transport core stays separate from subscription logic
- device binding stays separate from tunnel driver logic
- bundle issuance is denied if entitlement fails
- no reusable plaintext configs as the main user-facing path
- mobile support must not depend on MAC or private device identifiers

## Risk Register

### Risk 1: Too Early Payment Integration

Effect:

- product logic becomes tangled with payment provider details

Mitigation:

- implement manual subscription operations first

### Risk 2: Client Starts Before Bundle Contract Is Stable

Effect:

- client rework cost becomes high

Mitigation:

- define bundle envelope before client runtime implementation

### Risk 3: Device Identity Uses Weak Signals

Effect:

- copied access becomes easy

Mitigation:

- use app-generated device keypair as primary identity

### Risk 4: Repo Fragmentation Too Early

Effect:

- coordination overhead grows during alpha

Mitigation:

- keep backend and client in the same repo for now

## Success Criteria for v0.3

v0.3 should be considered successful if:

- current alpha remains installable
- ONX can model users/subscriptions/devices
- device limit is enforced
- lifetime subscriptions work
- bundle issuance is gated by entitlement
- first desktop client can connect using a device-bound bundle

## Immediate Next Step

The immediate next work item after this roadmap should be:

1. run the clean-server alpha acceptance checklist

Then:

2. start the `users / plans / subscriptions / devices` schema and API slice
