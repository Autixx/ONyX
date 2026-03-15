# ONX Windows Client Runtime Architecture

## Purpose

This document defines the target runtime architecture for the ONX Windows desktop VPN client.

It replaces the earlier simplified model where the GUI process directly executed local tunnel commands.

The new target model is:

- normal-user GUI process
- privileged Windows service daemon
- local named-pipe IPC between GUI and daemon
- all transport execution delegated to pre-bundled binaries under `apps/client-desktop/bin/`

The GUI must never require operator shell access or system-wide transport installation.

## Scope

This document covers:

- binary layout
- process model
- IPC contract
- runtime adapter boundaries
- config generation boundaries
- DNS enforcement ownership
- migration path from the current prototype

This document does not define:

- commercial packaging
- installer UX
- MSI authoring
- mobile client behavior

## Design Drivers

The runtime architecture must satisfy these constraints.

1. The client does not implement VPN protocols in Python.
2. The client manages external binaries only.
3. All privileged operations must run outside the GUI.
4. The GUI must remain usable in a normal user session.
5. The GUI must not expose protocol details in normal UX.
6. The runtime must work with pre-bundled binaries only.
7. Process management must use `asyncio.create_subprocess_exec`.

## Binary Layout

The canonical binary layout is:

```text
apps/client-desktop/
  bin/
    wireguard.exe
    wg.exe
    amneziawg.exe
    awg.exe
    openvpn.exe
    ck-client.exe
    xray.exe
    wintun.dll
```

Rules:

- `wireguard.exe` manages WireGuard tunnels via:
  - `/installtunnelservice <conf>`
  - `/uninstalltunnelservice <name>`
- `amneziawg.exe` plays the same role for AWG tunnels.
- `wg.exe` and `awg.exe` are CLI helpers.
- `wintun.dll` is side-by-side with the tunnel manager binaries.
- `ck-client.exe` runs first for `OpenVPN + Cloak`.
- `openvpn.exe` connects through the local Cloak port.
- `xray.exe` handles the supported L7 protocols and xHTTP-capable flows.

No system-wide installation is assumed.

## Process Model

The Windows client consists of two processes.

### 1. GUI Process

Responsibilities:

- login / registration UI
- bundle request and decrypt
- tray lifecycle
- cached local session view
- user-facing status and telemetry rendering
- local named-pipe client

The GUI process must not:

- install tunnel services
- change firewall state
- change system DNS state
- directly spawn privileged tunnel managers

### 2. Privileged Daemon Process

Responsibilities:

- run as Windows service via `pywin32`
- own all privileged transport actions
- own tunnel lifecycle
- own DNS and firewall enforcement
- own child process lifecycle for transport binaries
- return status and counters to GUI

The daemon process must not:

- render UI
- own long-term user identity state beyond what is needed for active runtime sessions

## Local IPC

The GUI and daemon communicate over a local Windows named pipe.

Canonical pipe name:

```text
\\.\pipe\onyx-client-daemon-v1
```

One request produces one response.

Recommended framing:

- UTF-8 JSON
- length-prefixed or message-mode pipe
- one command envelope per request

### Command Envelope

```json
{
  "request_id": "uuid-or-random-id",
  "command": "status",
  "payload": {}
}
```

### Response Envelope

```json
{
  "request_id": "same-id",
  "ok": true,
  "result": {},
  "error": null
}
```

## Initial IPC Commands

The first runtime version should support these commands.

### `ping`

Used by the GUI to verify the daemon is reachable.

### `status`

Used by the GUI to get current daemon state.

Response should include:

- running / idle / connected / error
- active transport kind
- active profile id
- active interface or tunnel name
- current DNS enforcement state
- current firewall enforcement state
- current rx/tx totals
- current rx/tx rates
- last runtime error

### `apply_bundle`

Supplies a decrypted bundle or a reduced runtime projection to the daemon.

### `connect`

Requests a connection using one runtime profile.

### `disconnect`

Stops active transport and clears enforcement state.

### `runtime_diagnostics`

Returns:

- presence of required binaries
- binary paths
- whether `wintun.dll` is present
- adapter readiness summary

### `traffic_stats`

Returns:

- current rx bytes
- current tx bytes
- current rx rate
- current tx rate
- active session uptime

## Runtime Adapters

The daemon must isolate each transport family behind an adapter interface.

Recommended adapter set:

- `WireGuardTunnelAdapter`
- `AmneziaWGTunnelAdapter`
- `OpenVpnCloakAdapter`
- `XrayAdapter`

Each adapter must own:

- binary validation
- config materialization
- connect command
- disconnect command
- status command
- cleanup logic

## WireGuard Adapter

Managed binaries:

- `wireguard.exe`
- `wg.exe`
- `wintun.dll`

Connect flow:

1. generate or materialize tunnel config
2. write config to daemon runtime dir
3. execute:
   - `wireguard.exe /installtunnelservice <conf>`
4. wait for service install result
5. publish active tunnel metadata

Disconnect flow:

1. execute:
   - `wireguard.exe /uninstalltunnelservice <name>`
2. remove temporary runtime material if safe

## AWG Adapter

Managed binaries:

- `amneziawg.exe`
- `awg.exe`
- `wintun.dll`

Connect flow mirrors WireGuard, but uses `amneziawg.exe`.

## OpenVPN + Cloak Adapter

Managed binaries:

- `ck-client.exe`
- `openvpn.exe`

Connect flow:

1. generate cloak client config
2. start `ck-client.exe`
3. wait until local proxy port is listening
4. generate OpenVPN config pointing to Cloak local port
5. start `openvpn.exe`
6. treat both child processes as one logical runtime session

## Xray Adapter

Managed binary:

- `xray.exe`

Supported protocol families:

- VLESS
- VMess
- Trojan
- Hysteria2
- xHTTP-capable Xray transport modes defined by the issued client profile

Connect flow:

1. generate JSON config as Python dict
2. write temp config file
3. execute:
   - `xray.exe run -config <tempfile.json>`

## Config Generation

### WG / AWG

Config generation uses `wgconfig`.

The preferred flow is:

1. GUI decrypts bundle
2. GUI sends a reduced runtime profile payload to daemon
3. daemon materializes final config file using trusted local generation logic

### Xray

The daemon builds JSON config from a Python dict and writes it to a temporary file.

## DNS and Firewall Ownership

DNS and firewall enforcement belong to the privileged daemon, not the GUI.

That includes:

- interface DNS assignment
- firewall guard rules
- `force_doh` enforcement
- cleanup after disconnect or crash recovery

The GUI may display state, but must not own these operations.

## Runtime State Directories

Recommended per-user local runtime home:

```text
%USERPROFILE%\.onyx-client\
```

Recommended daemon-owned subdirectories:

- `runtime/`
- `logs/`

Bundled immutable binaries stay under:

```text
apps/client-desktop/bin/
```

## Migration From Current Prototype

Current prototype behavior:

- GUI executes runtime directly
- GUI applies DNS directly
- GUI manages local subprocesses directly

Target migration:

### Phase 1

- add daemon process skeleton
- add named-pipe contract
- add runtime adapter skeletons
- keep GUI direct runtime unchanged

### Phase 2

- move WG/AWG runtime actions from GUI to daemon
- GUI becomes a pure IPC client for connect/disconnect

### Phase 3

- move DNS/firewall enforcement fully into daemon
- remove direct runtime execution from GUI

### Phase 4

- add OpenVPN+Cloak and Xray adapters
- add richer runtime diagnostics and recovery

## First Implementation Target

The first practical implementation after this document should be:

1. daemon service skeleton
2. named-pipe request/response layer
3. WG/AWG adapter skeleton
4. `status`, `runtime_diagnostics`, `connect`, `disconnect` commands
5. GUI wiring only after daemon side is stable

This ordering minimizes breakage.
