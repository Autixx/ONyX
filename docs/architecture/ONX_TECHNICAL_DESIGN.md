# ONX / ONyX Technical Design

## Status

Draft v0.1

## Purpose

This document defines the technical shape of `ONX` (`ONyX` as the product name), the core terms, the architectural boundaries, and the implementation sequence.

This is not end-user documentation. It is the source-of-truth design note for backend, agent, API, routing, and transport orchestration decisions.

## Product Definition

`ONX` is a control plane and orchestration system for heterogeneous overlay transport networks.

The system is built around:

- L3/L4 overlay and tunnel orchestration first
- optional L7 routing and proxying second
- multi-node, multi-hop, relay, and egress topologies
- centralized desired state with distributed node execution
- transport-driver abstraction instead of protocol-specific hardcoding

`ONyX` is not a classic CDN and not a classic proxy panel.

It is closer to:

- overlay network orchestrator
- transport mesh controller
- relay and egress fabric manager
- multi-protocol network control plane

## Goals

- Orchestrate point-to-point and mesh links between independent nodes
- Support heterogeneous transport backends via pluggable drivers
- Build site-to-site, gateway-relay-egress, and multi-hop topologies
- Apply traffic policies by route, destination, geo, balancer, and DNS interception
- Collect health, handshake, traffic, and speed-test data
- Provide a topology graph showing nodes, links, policies, and failures
- Let operators deploy and reconfigure links from the control plane without manual shell access in the common path

## Non-Goals

- Not a cache CDN
- Not an L7 proxy panel only
- Not a single-protocol mesh tied to one engine
- Not a pure SD-WAN replacement in the first releases
- Not a full zero-touch bootstrap platform in v1

## Core Positioning

The system uses L3/L4 overlays as the base fabric.

L7 engines are optional and may be attached later as additional transport or service modules, but they do not define the core architecture.

## Terminology

### Node

An independently managed server or appliance participating in the ONX network.

A node may act as:

- gateway
- relay
- egress
- mixed

### Link

A logical transport relationship between two nodes.

A link is defined by:

- transport driver
- left node
- right node
- addressing
- authentication material
- transport-specific parameters
- health and deployment status

Examples:

- AWG site-to-site tunnel
- WireGuard point-to-point link
- OpenVPN tunnel
- IPSec/IKEv2 tunnel
- Hysteria2 relay path

### Transport Driver

A backend-specific adapter implementing the ONX driver contract.

Examples:

- `awg`
- `wg`
- `openvpn`
- `ikev2_ipsec`
- `l2tp_ipsec`
- `softether`
- `sstp`
- `pptp` (legacy and discouraged, but representable)
- `xray`
- `hysteria2`
- `cloak`

### Overlay Transport

A transport capable of forming L3/L4 connectivity between nodes and carrying routed traffic.

Initial overlay transport families:

- `awg`
- `wg`
- `openvpn`
- `ikev2_ipsec`
- `l2tp_ipsec`
- `softether`
- `gre_ipsec` or `gre_protected`
- `sstp`

Legacy or discouraged but still modelable:

- `pptp`

Overlay transport requirements:

- carries routed traffic or full-tunnel traffic
- can be used as a next-hop or relay substrate
- has measurable transport health
- can be provisioned and applied predictably

### Proxy Transport

A transport or service engine primarily intended for session or stream forwarding instead of core routed overlay fabric.

Examples:

- `xray`
- `vless`
- `trojan`
- `hysteria2`
- `cloak`
- `httpt`

Proxy transports may later be used as:

- service egress modules
- special-purpose relay modules
- optional L7 routing providers

They are not the base data-plane abstraction of ONX.

### Policy

A routing or handling rule attached to ingress traffic, destination classes, DNS, or service groups.

Examples:

- direct
- next-hop
- balancer
- geo direct
- geo multihop
- forced local DNS interception

### Balancer

A policy target selecting one of multiple candidate links or egresses using a strategy.

Initial methods:

- `random`
- `leastload`
- `leastping`

### Probe

A system-generated connectivity or performance check.

Examples:

- handshake probe
- ping probe
- TCP probe
- UDP probe
- local speedtest between nodes

### Desired State

The normalized configuration stored in ONX which describes what the network should look like.

### Applied State

The actual state currently rendered and applied on a node.

### Drift

A mismatch between desired state and applied state.

## Architectural Model

ONX is split into three primary layers.

### 1. Control Plane

Responsibilities:

- stores desired state
- provides REST API
- schedules validation and deployment jobs
- computes topology and policy plans
- gathers status and probe results

### 2. Data Plane

Responsibilities:

- carries user traffic
- consists of transport engines, tunnel interfaces, proxy processes, and route rules
- is not tied to one protocol family

### 3. Node Execution Layer

Responsibilities:

- renders configs
- applies configs locally
- reports capabilities and health
- performs rollback when apply fails

This layer may start as SSH-based remote execution and later evolve into a lightweight ONX agent.

## Why ONX Is Not Just Nebula

Nebula and ONX overlap conceptually in that both operate in mesh-like network topologies.

However, ONX differs fundamentally in scope and architecture.

### Nebula Characteristics

Nebula is best understood as:

- a single overlay data-plane technology
- one protocol family
- one opinionated security and identity model
- one mesh implementation with lighthouse-assisted discovery

Nebula solves:

- secure host-to-host overlay networking
- node identity and reachability inside one mesh system

### ONX Characteristics

ONX is intended to be:

- a control plane, not one single tunnel protocol
- a heterogeneous transport orchestrator
- a policy engine across multiple transport classes
- a topology manager for relay, gateway, egress, and balancer roles
- an observability and deployment platform

ONX solves:

- how nodes are modeled
- how links are created across different technologies
- how policies are applied
- how traffic is routed between direct, multihop, balancer, geo, and DNS paths
- how state is deployed and monitored centrally

### Practical Difference

Nebula could theoretically become one future ONX transport driver or one supported overlay backend.

ONX itself is the system above that layer.

In short:

- Nebula is a mesh transport implementation
- ONX is a mesh and transport orchestration platform

## Domain Model

The initial normalized model should contain the following entities.

### Node

Fields:

- `id`
- `name`
- `role`
- `management_address`
- `ssh_host`
- `ssh_port`
- `ssh_user`
- `auth_type`
- `auth_secret_ref`
- `capabilities`
- `status`

### Driver

Fields:

- `name`
- `kind`
- `mode`
- `capabilities`
- `version_constraints`

Kinds:

- `overlay`
- `proxy`
- `service`

Modes:

- `l3_overlay`
- `l4_tunnel`
- `l7_proxy`

### Link

Fields:

- `id`
- `name`
- `driver_name`
- `left_node_id`
- `right_node_id`
- `topology_type`
- `state`
- `desired_spec`
- `applied_spec`
- `health_summary`

Topology types:

- `p2p`
- `upstream`
- `relay`
- `balancer_member`
- `service_edge`

### Link Endpoint

Fields:

- `id`
- `link_id`
- `node_id`
- `interface_name`
- `listen_port`
- `address_v4`
- `address_v6`
- `mtu`
- `table_mode`
- `endpoint`

### Credential Material

Fields:

- `id`
- `owner_type`
- `owner_id`
- `kind`
- `secret_ref`

### Route Policy

Fields:

- `id`
- `node_id`
- `ingress_ref`
- `action`
- `target_ref`
- `routed_networks`
- `excluded_networks`
- `priority`
- `enabled`

Actions:

- `direct`
- `next_hop`
- `balancer`

### Geo Policy

Fields:

- `id`
- `route_policy_id`
- `country_code`
- `mode`
- `target_ref`

Modes:

- `direct`
- `multihop`
- `balancer`

### DNS Policy

Fields:

- `id`
- `node_id`
- `ingress_ref`
- `enabled`
- `dns_address`
- `capture_protocols`
- `capture_ports`
- `exceptions`

### Balancer

Fields:

- `id`
- `name`
- `method`
- `member_refs`
- `health_policy`

### Probe Result

Fields:

- `id`
- `probe_type`
- `source_ref`
- `target_ref`
- `status`
- `metrics`
- `created_at`

### Job

Fields:

- `id`
- `kind`
- `target_type`
- `target_id`
- `state`
- `request_payload`
- `result_payload`
- `created_at`
- `updated_at`

## Driver Contract

Every transport driver must implement the same backend contract.

Required operations:

- `validate(spec, context)`
- `render(spec, context)`
- `apply(spec, context)`
- `destroy(spec, context)`
- `status(spec, context)`
- `stats(spec, context)`
- `health(spec, context)`
- `rollback(spec, context)`
- `supports(feature)`

This prevents the rest of the system from becoming protocol-specific.

## Routing Model

The routing layer must be independent from any one transport.

Core path selection modes:

- direct via node main uplink
- next-hop via overlay link
- balancer-selected next-hop
- geo-based direct
- geo-based multihop
- forced local DNS interception

The first implementation may continue using policy routing and packet marking on Linux, but ONX should model the intent rather than Linux command strings.

## Deployment Model

### Phase 1

Deployment over SSH only.

Requirements:

- Ubuntu 22.04 and 24.04 support first
- idempotent remote execution
- config preview before apply
- rollback on partial failure

### Phase 2

Optional ONX agent.

Agent responsibilities:

- receive signed apply requests
- report capabilities
- execute driver actions
- return structured status

## Control Plane Availability

ONX must distinguish between:

- data plane survivability
- control plane survivability

An already deployed transport network may continue carrying traffic even if the current control node is lost, but the system becomes partially or fully unmanaged without a surviving control-plane path.

The chosen long-term strategy is:

- v1: single control node plus encrypted off-node backups
- v2: three control-plane nodes with replication and failover
- no database sharding in the early architecture stages

This decision is formalized in:

- `ADR-0004-control-plane-ha.md`

## Observability Model

ONX must expose:

- link status
- handshake age
- transfer counters
- latency
- packet loss where possible
- probe history
- deployment logs
- drift between desired and applied state

## Visual Topology Model

The UI graph should be derived from backend topology data, not hand-crafted frontend state.

Graph nodes:

- managed nodes
- optional logical groups
- optional balancers

Graph edges:

- transport links
- policy targets
- relay relationships

Edge labels:

- driver
- interface
- endpoint
- handshake status
- selected policy mode

## Security Model

Initial assumptions:

- operator-controlled infrastructure
- SSH credentials stored as secrets
- key material separated from plain config objects
- audit trail for applies and deletes

Later:

- role-based access control
- agent mutual authentication
- signed job execution

## API-First Development Rule

The project must evolve in this order:

1. terms
2. domain model
3. REST schemas
4. validation and apply logic
5. UI

The UI must never become the source of truth for business logic.

## Initial API Surface

Versioned prefix:

- `/api/v1`

Initial groups:

- `/nodes`
- `/drivers`
- `/links`
- `/policies`
- `/balancers`
- `/dns-policies`
- `/probes`
- `/graph`
- `/jobs`

## First Implementation Sequence

### Stage 0. Terminology and ADR

Deliverables:

- this design document
- architecture decisions for node, link, driver, policy, and deployment concepts

### Stage 1. ONX Backend Skeleton

Deliverables:

- `onx/` directory
- FastAPI application
- SQLAlchemy models
- Alembic migrations
- base health endpoint

### Stage 2. Node Registry

Deliverables:

- node CRUD
- SSH credentials
- capability discovery
- ping and SSH probes

### Stage 3. AWG Driver

Deliverables:

- AWG driver contract implementation
- render/apply/status/stats support
- site-to-site deploy via SSH

### Stage 4. Generic Link Orchestration

Deliverables:

- normalized `Link` creation flow
- left/right endpoint specs
- rollback and validation

### Stage 5. Route Policy Engine

Deliverables:

- direct
- next-hop
- balancer
- excluded networks
- geo rules
- DNS capture

### Stage 6. Health and Speed Probes

Deliverables:

- handshake probe
- latency probe
- node-to-node speedtest
- link scoring for balancers

### Stage 7. Topology Graph

Deliverables:

- topology API
- health overlays
- ONyX dark UI graph

### Stage 8. Additional Drivers

Suggested order:

1. `wg`
2. `openvpn`
3. `ikev2_ipsec`
4. `xray`
5. `hysteria2`
6. `cloak`

The exact order may change, but no new driver should be added before the driver contract is stable.

## Design Constraints

- Backend is the source of truth
- Desired state must be explicit and serializable
- Every apply action must be idempotent
- Rollback must exist before high-risk automation
- Mixed transports must be normalized through drivers, not special cases
- L7 support must remain optional and layered on top of the base overlay fabric

## Open Questions

- When should SSH-based execution be replaced by an ONX agent
- Which transports remain first-class in v1 and which are experimental
- Whether speedtest should be built-in only or optionally integrate with `iperf3`
- How far to support legacy VPN protocols such as PPTP in a modern secure deployment
- Whether Nebula should eventually be implemented as an ONX overlay driver

## Immediate Next Step

The next document should define:

- repository structure for `onx/`
- Python dependency set
- database schema draft
- first REST endpoints for `Node` and `Link`
