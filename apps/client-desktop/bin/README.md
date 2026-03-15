# ONyX Bundled Runtime Binaries

This directory is reserved for the Windows runtime binaries used by the privileged ONyX client daemon.

Expected layout:

```text
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

- binaries are bundled with the project
- no system-wide installation is assumed
- the GUI must not execute these binaries directly
- the privileged daemon owns all runtime process execution

Do not place unofficial or random third-party builds here.

Use only the exact binaries selected for ONyX distribution.
