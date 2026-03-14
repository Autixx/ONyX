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
- real local tunnel connect/disconnect for AWG and WG when encrypted bundle contains runtime profiles
- first-run splash screen
- system tray lifecycle
- interactive background startup task for Windows user sessions

Not implemented yet:

- host DNS enforcement
- protocol benchmarking and automatic transport race
- hardened secret vault
- production support-ticket submit flow

## Files

- `onyx_client.py` - main PyQt6 client
- `onyx_splash.py` - first-run splash screen
- `assets/icons/onyx.ico` - Windows application icon
- `assets/icons/onyx_*.png` - multi-resolution icon set for window/tray/app usage

## Install Dependencies

```bash
python -m pip install -r requirements.txt
```

For real tunnel runtime on the client machine you also need local transport tools in `PATH`:

- `awg.exe` and `awg-quick.exe` for AWG
- `wg.exe` and `wg-quick.exe` for WireGuard

The client does not install those tools for you yet.

Lookup order is:

1. `~/.onyx-client/bin`
2. system `PATH`

## Run

Normal launch:

```bash
python onyx_client.py
```

Start hidden in the tray:

```bash
python onyx_client.py --background
```

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

## Tray Behavior

- closing the window hides the client to tray
- tray menu actions:
  - `Open`
  - `Connect` / `Disconnect`
  - `Exit`

## Runtime Notes

- the client chooses the first working encrypted runtime profile from the issued bundle
- transport type stays hidden from the normal UI
- if the bundle contains no usable AWG/WG profile, connect will fail with a runtime error instead of faking success
- `Settings` now shows:
  - `AWG READY / WG READY / NO RUNTIME`
  - resolved tool paths
  - bundle runtime profile summary
  - DNS runtime design state
  - `Open Tools Folder` action

## DNS Status

- the bundle already carries DNS policy fields
- the client displays them in diagnostics
- host-level forced DNS is still not applied on the machine yet

## Icon Mapping

The icon set is used as follows:

- `onyx.ico` - Windows executable / application icon
- `onyx_16.png` - smallest tray-compatible size
- `onyx_32.png` - small app/window fallback
- `onyx_48.png`, `onyx_64.png` - standard desktop/window sizes
- `onyx_96.png`, `onyx_128.png`, `onyx_256.png` - high-DPI and launcher scaling
