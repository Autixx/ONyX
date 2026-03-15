# ONyX Desktop Client

This is the current PyQt6 desktop client for ONyX.

Current scope:

- client login/logout
- registration request submit
- local session persistence
- local X25519 device key generation
- device registration
- device challenge/verify
- encrypted bundle issue + local decrypt
- real local or daemon-backed runtime connect/disconnect for AWG, WG, and Xray when encrypted bundle contains runtime profiles
- first-run splash screen
- system tray lifecycle
- interactive background startup task for Windows user sessions
- Windows runtime-service skeleton for future privileged daemon split

Not implemented yet:

- host DNS enforcement
- protocol benchmarking and automatic transport race
- hardened secret vault
- production support-ticket submit flow

## Files

- `onyx_client.py` - main PyQt6 client
- `onyx_splash.py` - first-run splash screen
- `onyx_daemon_service.py` - Windows privileged daemon skeleton
- `onyx_runtime_selftest.py` - runtime readiness self-test
- `runtime/` - named-pipe, service, and transport adapter skeleton
- `bin/` - reserved bundled-binary layout for future runtime
- `assets/icons/onyx.ico` - Windows application icon
- `assets/icons/onyx_*.png` - multi-resolution icon set for window/tray/app usage

## Install Dependencies

```bash
python -m pip install -r requirements.txt
```

For the Windows daemon skeleton you will also need:

```bash
python -m pip install pywin32
```

The current GUI prototype still supports the older direct-runtime path.

The target Windows architecture is different:

- bundled binaries under `apps/client-desktop/bin/`
- privileged runtime operations in `onyx_daemon_service.py`
- GUI-to-daemon communication over a local named pipe

The bundled `bin/` layout is documented in:

- `apps/client-desktop/bin/README.md`
- `docs/architecture/ONX_WINDOWS_CLIENT_RUNTIME_ARCHITECTURE.md`

For the current migration step, bundled binaries placed in `apps/client-desktop/bin/` are treated as the primary runtime source.

## Run

Normal launch:

```bash
python onyx_client.py
```

Start hidden in the tray:

```bash
python onyx_client.py --background
```

Run runtime self-test:

```bash
python onyx_runtime_selftest.py
```

Skip daemon spawn and only validate files/dependencies:

```bash
python onyx_runtime_selftest.py --skip-daemon
```

Run real WG/AWG tunnel smoke through the daemon:

```bash
python onyx_runtime_selftest.py --with-tunnel-smoke
```

Run real Xray process smoke through the daemon:

```bash
python onyx_runtime_selftest.py --with-xray-smoke
```

This last mode requires:

- Windows
- Administrator privileges
- `pywin32`
- bundled WG/AWG binaries present in `apps/client-desktop/bin/`

## Windows Background Startup

This client is intentionally installed as an interactive startup task, not as a true Windows service.

Reason:

- a real Windows service is the wrong model for a GUI tray application
- tray icons and interactive windows must run in the user session

Install startup task for the current user:

```bash
python onyx_client.py --install-startup
```

Alias kept for operator convenience:

```bash
python onyx_client.py --install-service
```

Remove startup task:

```bash
python onyx_client.py --uninstall-startup
```

Alias:

```bash
python onyx_client.py --uninstall-service
```

## Windows Runtime Daemon Skeleton

Run the privileged daemon skeleton in console mode:

```bash
python onyx_daemon_service.py --console
```

Install / remove the Windows service skeleton:

```bash
python onyx_daemon_service.py install
python onyx_daemon_service.py remove
```

This skeleton is intentionally separate from the current GUI runtime path.

It exists to support the next migration step:

- move privileged transport actions out of the GUI
- keep the GUI as a normal-user process
- use a local named pipe for IPC

## Tray Behavior

- closing the window hides the client to tray
- tray menu actions:
  - `Open`
  - `Connect` / `Disconnect`
  - `Exit`

## Runtime Notes

- the client chooses the first working encrypted runtime profile from the issued bundle
- transport type stays hidden from the normal UI
- if the bundle contains no usable AWG/WG/Xray profile, connect will fail with a runtime error instead of faking success
- the current direct-runtime path is transitional and will be replaced by the privileged daemon path defined in the Windows runtime architecture document
- `Settings` now shows:
  - `AWG READY / WG READY / XRAY READY / NO RUNTIME`
  - resolved tool paths
  - bundle runtime profile summary
  - DNS runtime design state
  - `Open Tools Folder` action

## DNS Status

- the bundle carries DNS policy fields from ONyX backend config
- on Windows, the client applies the issued resolver to the active tunnel interface on connect
- on disconnect, the tunnel interface DNS is reset back to DHCP
- when `force_doh=true`, the client also installs temporary Windows Firewall rules while connected:
  - blocks outbound TCP/UDP 853 (DoT / DoQ-style fallback)
  - blocks outbound TCP/UDP 443 to common public DNS resolver IPs
- this is a pragmatic enforcement layer, not a perfect generic HTTPS-level DoH detector

## Icon Mapping

The icon set is used as follows:

- `onyx.ico` - Windows executable / application icon
- `onyx_16.png` - smallest tray-compatible size
- `onyx_32.png` - small app/window fallback
- `onyx_48.png`, `onyx_64.png` - standard desktop/window sizes
- `onyx_96.png`, `onyx_128.png`, `onyx_256.png` - high-DPI and launcher scaling
