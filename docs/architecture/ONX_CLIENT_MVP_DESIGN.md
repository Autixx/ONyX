# ONX Client MVP Design

## Status

Draft v0.1

## Purpose

This document defines the first real ONX end-user client.

It fixes:

- what the user must see
- what the user must not see
- how the client authenticates
- how the client receives runtime access
- how protocol selection should work
- how DNS enforcement should work
- what backend modules are required before implementation starts

This is a product and technical design note for the client MVP.

It complements:

- `ONX_CLIENT_DELIVERY_ARCHITECTURE.md`
- `ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md`
- `ONX_SUBSCRIPTIONS_AND_BILLING.md`

## Product Goal

The ONX client must behave like a normal consumer VPN application for the end user while still using a multi-hop, multi-protocol control-plane internally.

The client must:

- hide transport complexity from ordinary users
- avoid exposing reusable plaintext configs
- receive runtime access online from ONX
- select the best viable transport automatically
- show only the operational information the user actually needs

## Non-Goals

The MVP client is not:

- a power-user tunnel editor
- a raw config importer/exporter
- a topology viewer
- a protocol laboratory UI
- a full device management cabinet

The client must not expose internal transport structure as a normal UX path.

## User-Visible Surface

The user should see only:

### 1. Login Window

Fields:

- username or email
- password

Actions:

- sign in
- open registration window if account does not exist
- show password reset entry later, but not required for MVP

### 2. Registration Window

Fields:

- username
- password
- password confirmation
- last name
- first name
- email
- referral code
- planned device count (`1..3`)
- usage goal:
  - `internet`
  - `gaming`
  - `development`

Validation rules:

- password and confirmation must match
- username and email format must be validated locally before submit
- device count is an intent hint, not a hard entitlement guarantee

### 3. Main Client Window

Must show:

- connection status: `Enabled / Disabled`
- currently connected / disconnected state
- used traffic volume
- live ingress and egress throughput
- configuration expiration date
- support request entry point

The user should not need to know:

- which tunnel protocol is active
- how many hops are used
- which node is ingress vs relay vs egress

### 4. Support Request Window

Minimum fields:

- issue type
- free-text description
- optional attachment later

Client should be able to attach:

- client version
- OS version
- current session id if present
- recent connection diagnostics

This data should be attached automatically unless the user opts out.

## User-Hidden Surface

The client must avoid exposing the following in its normal UX:

### 1. Virtual Interface

The user should not be shown the created tunnel interface inside the application UI.

The OS may still show it in system network settings. That is acceptable.

### 2. Split Tunnel Internals

The user should not be shown:

- which prefixes are routed directly
- which traffic goes through overlay
- whether traffic is single-hop or multi-hop

### 3. Forced DNS Path

The user should not be shown:

- that DNS is forcibly redirected
- that system DNS settings are overridden at runtime
- that DoH/DoT interception or resolver redirection is happening

The client may optionally expose only a simple label such as:

- `Protected DNS: On`

### 4. Connection Configuration

The user must not receive:

- plaintext `.conf`
- plaintext endpoint inventory
- plaintext protocol configuration blocks

The client should receive only encrypted runtime bundle data and unpack it internally.

### 5. Transport Protocol

The user should not normally see:

- AWG
- WG
- OpenVPN
- Xray
- fallback chain

This may exist only in diagnostic mode later, not in standard UX.

## Authentication and Session Model

## Core Requirement

The client must use real web-style session auth for user login, but local app session state must survive short offline periods.

## Recommended Model

Use two layers:

### Layer A: Server Session / Access Token

Used for:

- authentication against ONX
- registration requests
- bundle issuance
- support requests

This is online-only.

### Layer B: Local App Session State

Used for:

- unlocking the client UI while offline
- showing cached account status
- showing cached expiration / traffic / last connection state

This is not enough to establish a new tunnel if online verification is required and the cached runtime bundle has expired.

## Offline Requirement

If the user has logged in before, the client should still open while offline and show:

- account identity
- last known traffic usage
- last known expiration date
- last known connection state

But while offline the client must not:

- refresh expired bundle
- register a new device
- change credentials
- submit support request unless queued locally

## Session Persistence

Recommended behavior:

- login success creates server-side authenticated session
- client stores local session marker in secure storage
- if internet is unavailable, client may still unlock locally
- if internet is available, client refreshes account/session state immediately

This is better than relying only on browser-like cookies.

For desktop app:

- use secure local storage
- do not store raw password
- store only app session state and encrypted refresh material if implemented later

## Registration and Identity Model

The registration screen is user registration, not only device registration.

That means the backend must eventually support:

- `users`
- `subscriptions`
- `devices`
- device-bound session bundle issuance

Recommended registration flow:

1. user submits registration form
2. ONX creates registration request
3. operator approves or auto-approves by policy
4. client proceeds to authenticated login
5. client registers its device identity

This maps well to the already added `registrations` module.

## Device Identity

The client must generate its own device keypair.

This is the primary device binding anchor.

It must not rely on:

- MAC address
- IMEI
- serial number
- any unstable or privacy-hostile identifier

Desktop device signals may be stored as metadata only.

Mobile support later should use platform secure storage:

- Android Keystore
- iOS Keychain / Secure Enclave

## Runtime Access Delivery

## Important Rule

The client must not obtain user runtime configuration from the admin panel as UI.

The correct source is:

- dedicated client delivery API inside the same ONX backend deployment

This is the recommended near-term model:

- one backend deployment
- one database
- separate admin API and client API contours

## Why This Is Better

The client bundle must be generated at issue time because ONX must check:

- user status
- subscription status
- device registration
- device limit
- current health of ingress candidates
- current transport availability

So the client should receive:

- dynamic encrypted runtime bundle

Not:

- stored reusable config file

## First MVP Bundle Contents

The client bundle should contain only:

- `bundle_id`
- `user_id`
- `device_id`
- `issued_at`
- `expires_at`
- `transport_candidates`
- `dns_target`
- `policy_hints`
- integrity/authenticated encryption data

It should not contain:

- full node inventory
- relay graph
- admin-only route policies
- all possible backend nodes

## Transport and Protocol Selection

## Client Requirement

At first launch the client must test all locally supported transport variants and pick the best viable one for the current user goal.

## User Goals

The registration goal field must feed protocol preference:

### `internet`

Prefer:

- stable throughput
- censorship resistance
- low reconnect frequency

### `gaming`

Prefer:

- lowest latency
- lowest jitter
- fastest reconnect

### `development`

Prefer:

- stable throughput
- predictable latency
- better handling for mixed interactive + bulk traffic

## Selection Inputs

The client should measure per candidate:

- connect success / failure
- handshake success
- RTT / ping
- short burst throughput estimate
- DNS reachability through tunnel

## Selection Output

The client should choose:

- one active protocol candidate
- one or more fallback candidates

The chosen protocol should remain hidden from the normal UI.

## DNS Enforcement

## Requirement

All DNS requests must be forced to the resolver defined in the user runtime bundle.

This includes:

- classic system DNS
- local stub resolvers
- attempts to bypass via explicit DoH where technically interceptable on the client platform

## MVP Scope

Desktop MVP should implement:

- system resolver override while connected
- forced DNS target from bundle
- runtime verification that DNS actually resolves through the protected path

If the platform allows practical interception/enforcement beyond plain resolver override, it may be added later.

But the client UX must still present this simply as:

- protected DNS enabled

not as a technical DNS policy editor.

## Traffic and Speed Display

The user needs:

- cumulative used traffic
- current ingress throughput
- current egress throughput

Recommended semantics:

- cumulative traffic should come from ONX entitlement/accounting source of truth
- live ingress/egress speed should come from client runtime counters

Do not try to infer live speed only from server-side delayed reports.

The client runtime should expose local counters for:

- bytes received
- bytes sent
- rolling 1s / 5s rate

## Configuration Expiration

The client should display:

- subscription expiration or bundle validity expiration, whichever is relevant to the user

Recommended display:

- user-facing primary field: service expiration date
- optional secondary diagnostic field: session/bundle refresh validity

Do not confuse these two in UX.

## Support Flow

The client must offer a simple support request path.

Recommended backend shape later:

- `POST /api/v1/support/tickets`

Minimum payload:

- user id from session
- device id
- app version
- OS info
- current connection state
- message text

If offline:

- queue locally
- submit when network returns

## Backend Requirements for Client MVP

The following backend capabilities are required before the full client can work:

### Required

- user auth for client
- user registration request flow
- users / subscriptions / devices model
- device registration
- device challenge-response
- encrypted bundle issuance
- bundle refresh / rebind
- support request endpoint

### Already Partially Present

- client routing protocol
- best ingress logic
- session rebind logic
- node traffic and path planner primitives

### Not Yet Sufficient By Themselves

- admin web auth
- admin UI login
- admin bearer/JWT auth
- admin registrations/peers views

These are operator-side, not end-user client auth.

## Recommended Deployment Model

For MVP:

- keep one ONX backend deployment
- keep one PostgreSQL database
- expose client delivery API from the same backend
- do not make the admin panel the runtime config source

Recommended logical split:

- admin API: operator only
- client API: app only

Same deployment is fine.

Separate delivery gateway can come later.

## Recommended Repository Layout

Client should start in the same repo:

```text
/apps
  /client-desktop

/libs
  /client-protocol
  /profile-envelope
  /crypto-utils
```

The first target should be desktop MVP.

Mobile comes later after the contract stabilizes.

## Security Boundaries

The client can protect against ordinary misuse:

- copying configs
- editing configs manually
- reusing config on another device

The client does not fully protect against:

- reverse engineering
- memory extraction
- root-level local inspection

This is acceptable for MVP.

The design target is practical anti-copy protection, not perfect secrecy against a hostile device owner.

## Explicit Product Decisions

### Decision 1

The client does not download plaintext config files.

### Decision 2

The client does not expose protocol selection in normal UX.

### Decision 3

The client obtains runtime access from dedicated client delivery API, not from the admin panel UI.

### Decision 4

The client may open offline after prior login, but offline mode is read-mostly and cannot refresh runtime access.

### Decision 5

The first client target is desktop.

## Suggested Implementation Sequence

1. finalize users / subscriptions / devices backend model
2. add client registration request flow
3. add device registration and challenge-response
4. define encrypted session bundle envelope
5. add client support ticket API
6. scaffold desktop client shell
7. implement login + registration
8. implement bundle retrieval
9. implement protocol benchmarking and selection
10. implement runtime connection management
11. implement support submission and cached offline state

## Exit Criteria for Client MVP

The first client MVP is complete when:

- user can register
- user can log in
- device can be bound to account
- client can fetch encrypted runtime bundle
- client can auto-select a viable transport
- client can connect and disconnect
- client shows traffic, speed, and expiration
- client can submit support request
- no plaintext reusable config is exposed in normal UX
