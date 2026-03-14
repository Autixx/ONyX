# ONyX Desktop Client Skeleton

This is the first desktop client bootstrap skeleton for ONyX.

Current scope:

- client registration
- client login/logout
- local session persistence
- local device keypair generation
- device registration
- device challenge/verify
- bundle issue + local bundle decryption
- basic dashboard state

Out of scope in this first skeleton:

- real VPN tunnel runtime
- DNS override on the host
- protocol benchmarking
- background reconnect daemon
- production-grade secure local secret storage

## Run

```bash
python onyx_client.py
```

## Prerequisites

Install the ONyX backend/client dependencies, or at minimum:

```bash
python -m pip install httpx cryptography
```

Tkinter is required and usually ships with the standard Python distribution.
