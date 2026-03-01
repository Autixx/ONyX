# ADR-0004: Control Plane High Availability Strategy

## Status

Accepted

## Context

ONX is intended to evolve toward a mesh-operated transport platform where operators can recover or continue management from more than one location.

The immediate architectural question is how ONX should survive the loss of a central control node.

Several options were considered:

- encrypted backups with manual restore after prolonged outage
- hot standby replicas with automatic failover
- fully distributed peer-to-peer control plane
- database sharding

The project does not need sharding in the early or medium stages. The primary issue is control-plane availability and recoverability, not database write scale.

The project also should not begin with a fully peer-to-peer control plane because that would move a large part of the complexity from transport orchestration into distributed consensus and conflict resolution before the core networking product is stable.

## Decision

ONX will follow this control-plane evolution path:

### v1

- single control-plane node
- one primary database
- encrypted off-node backups
- documented restore path

### v2

- three control-plane nodes
- one primary database
- two hot replicas
- automatic or semi-automatic failover
- API/UI reachable from any control-plane node
- job execution guarded by leader election or lease ownership
- secrets replicated as encrypted state

### v3

- optional future distributed or federated control-plane mode
- only after the core domain model, drivers, jobs, and rollback semantics are stable

This means:

- backups are required, but backups alone are not considered sufficient for the long-term target
- the preferred resiliency model is replication plus failover
- database sharding is explicitly rejected for the current architecture stages

## Consequences

### Positive

- preserves a practical implementation path
- avoids premature distributed-systems complexity
- gives a clear upgrade path from single-control to HA control
- aligns with the requirement that management should not disappear after the loss of one node

### Negative

- v1 still has a control-plane single point of failure
- v2 requires replication management, failover logic, and job leadership control
- secret storage and rotation become more complex in HA mode

### Constraints Introduced

- desired state must remain serializable and replicable
- jobs must be idempotent and safe to resume or deduplicate after failover
- audit trail and secret state must be recoverable across control-plane nodes
- control-plane failover must be designed before moving to a broader multi-driver rollout

## Rejected Options

### Backups Only as the Final Strategy

Rejected because this leaves the system without active management during the outage window.

### Database Sharding

Rejected because it solves scale partitioning rather than control-plane availability and would complicate strongly related entities such as nodes, links, jobs, and policies.

### Fully Distributed P2P Control Plane as the Starting Point

Rejected because it adds significant consensus, conflict, and recovery complexity too early in the project lifecycle.

