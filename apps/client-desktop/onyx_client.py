import base64
import json
from pathlib import Path
import secrets
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


APP_DIR = Path.home() / ".onyx-client"
STATE_PATH = APP_DIR / "state.json"


def b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64u_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))


class ClientState:
    def __init__(self) -> None:
        self.base_url = "http://127.0.0.1:8081/api/v1"
        self.session_token = ""
        self.user = None
        self.subscription = None
        self.device_id = ""
        self.device_private_key = ""
        self.device_public_key = ""
        self.last_bundle = None

    def load(self) -> None:
        if not STATE_PATH.exists():
            return
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        self.base_url = data.get("base_url", self.base_url)
        self.session_token = data.get("session_token", "")
        self.user = data.get("user")
        self.subscription = data.get("subscription")
        self.device_id = data.get("device_id", "")
        self.device_private_key = data.get("device_private_key", "")
        self.device_public_key = data.get("device_public_key", "")
        self.last_bundle = data.get("last_bundle")

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "base_url": self.base_url,
                    "session_token": self.session_token,
                    "user": self.user,
                    "subscription": self.subscription,
                    "device_id": self.device_id,
                    "device_private_key": self.device_private_key,
                    "device_public_key": self.device_public_key,
                    "last_bundle": self.last_bundle,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def clear_session(self) -> None:
        self.session_token = ""
        self.user = None
        self.subscription = None
        self.save()


class ONyXDesktopClient(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.state_store = ClientState()
        self.state_store.load()
        self.title("ONyX Desktop Client Skeleton")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(bg="#111820")
        self._build_ui()
        self._apply_cached_state()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        top = ttk.Frame(container)
        top.pack(fill="x")
        ttk.Label(top, text="Backend URL").pack(side="left")
        self.base_url_var = tk.StringVar(value=self.state_store.base_url)
        ttk.Entry(top, textvariable=self.base_url_var, width=48).pack(side="left", padx=8)
        ttk.Button(top, text="Save URL", command=self.save_base_url).pack(side="left")

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True, pady=(12, 0))

        self.login_frame = ttk.Frame(self.notebook, padding=12)
        self.register_frame = ttk.Frame(self.notebook, padding=12)
        self.dashboard_frame = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.login_frame, text="Login")
        self.notebook.add(self.register_frame, text="Registration")
        self.notebook.add(self.dashboard_frame, text="Dashboard")

        self._build_login_tab()
        self._build_register_tab()
        self._build_dashboard_tab()

    def _build_login_tab(self) -> None:
        self.login_username = tk.StringVar()
        self.login_password = tk.StringVar()
        form = ttk.Frame(self.login_frame)
        form.pack(anchor="nw", fill="x")
        ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.login_username, width=36).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Password").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.login_password, show="*", width=36).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(form, text="Login", command=self.login).grid(row=2, column=1, sticky="e", pady=10)
        form.columnconfigure(1, weight=1)

    def _build_register_tab(self) -> None:
        self.reg_vars = {
            "username": tk.StringVar(),
            "password": tk.StringVar(),
            "password_confirm": tk.StringVar(),
            "first_name": tk.StringVar(),
            "last_name": tk.StringVar(),
            "email": tk.StringVar(),
            "referral_code": tk.StringVar(),
            "requested_device_count": tk.StringVar(value="1"),
            "usage_goal": tk.StringVar(value="internet"),
        }
        form = ttk.Frame(self.register_frame)
        form.pack(anchor="nw", fill="x")
        fields = [
            ("Username", "username"),
            ("Password", "password"),
            ("Password Confirm", "password_confirm"),
            ("First Name", "first_name"),
            ("Last Name", "last_name"),
            ("Email", "email"),
            ("Referral Code", "referral_code"),
            ("Requested Devices (1-3)", "requested_device_count"),
            ("Usage Goal", "usage_goal"),
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", pady=5)
            kwargs = {"textvariable": self.reg_vars[key], "width": 36}
            if "password" in key:
                kwargs["show"] = "*"
            ttk.Entry(form, **kwargs).grid(row=idx, column=1, sticky="ew", pady=5)
        ttk.Button(form, text="Submit Registration", command=self.register).grid(row=len(fields), column=1, sticky="e", pady=10)
        form.columnconfigure(1, weight=1)

    def _build_dashboard_tab(self) -> None:
        top = ttk.Frame(self.dashboard_frame)
        top.pack(fill="x")
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(top)
        right.pack(side="right", fill="y")

        self.dashboard_summary = tk.Text(left, height=18, width=80)
        self.dashboard_summary.pack(fill="x")
        self.bundle_view = tk.Text(left, height=18, width=80)
        self.bundle_view.pack(fill="both", expand=True, pady=(12, 0))

        buttons = [
            ("Refresh Me", self.refresh_me),
            ("Register Device", self.register_device),
            ("Verify Device", self.verify_device),
            ("Issue Bundle", self.issue_bundle),
            ("Logout", self.logout),
        ]
        for text, handler in buttons:
            ttk.Button(right, text=text, command=handler).pack(fill="x", pady=4)

        self.log_view = tk.Text(self.dashboard_frame, height=10)
        self.log_view.pack(fill="x", pady=(12, 0))

    def log(self, message: str) -> None:
        self.log_view.insert("end", message + "\n")
        self.log_view.see("end")

    def save_base_url(self) -> None:
        self.state_store.base_url = self.base_url_var.get().strip().rstrip("/")
        self.state_store.save()
        self.log("Base URL updated.")

    def _headers(self) -> dict:
        headers = {}
        if self.state_store.session_token:
            headers["Authorization"] = f"Bearer {self.state_store.session_token}"
        return headers

    def _request(self, method: str, path: str, *, json_body=None):
        url = self.state_store.base_url + path
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, url, json=json_body, headers=self._headers())
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"{response.status_code}: {detail}")
        if response.status_code == 204:
            return None
        return response.json()

    def _apply_cached_state(self) -> None:
        if self.state_store.user:
            self.render_dashboard()
            self.notebook.select(self.dashboard_frame)

    def login(self) -> None:
        try:
            payload = {
                "username": self.login_username.get().strip(),
                "password": self.login_password.get(),
            }
            data = self._request("POST", "/client/auth/login", json_body=payload)
            self.state_store.session_token = data["session_token"]
            self.state_store.user = data["user"]
            self.state_store.subscription = data.get("active_subscription")
            self.state_store.save()
            self.render_dashboard()
            self.notebook.select(self.dashboard_frame)
            self.log("Login successful.")
        except Exception as exc:
            messagebox.showerror("Login Failed", str(exc))

    def register(self) -> None:
        try:
            payload = {key: var.get().strip() for key, var in self.reg_vars.items()}
            payload["requested_device_count"] = int(payload["requested_device_count"])
            self._request("POST", "/client/registrations", json_body=payload)
            messagebox.showinfo("Registration", "Registration request submitted.")
            self.log("Registration request submitted.")
        except Exception as exc:
            messagebox.showerror("Registration Failed", str(exc))

    def refresh_me(self) -> None:
        try:
            data = self._request("GET", "/client/auth/me")
            self.state_store.user = data["user"]
            self.state_store.subscription = data.get("active_subscription")
            self.state_store.save()
            self.render_dashboard()
            self.log("Refreshed client session state.")
        except Exception as exc:
            self.log(f"Refresh failed: {exc}")
            if self.state_store.user:
                self.render_dashboard(offline=True)

    def logout(self) -> None:
        try:
            if self.state_store.session_token:
                self._request("POST", "/client/auth/logout")
        except Exception as exc:
            self.log(f"Logout request failed: {exc}")
        self.state_store.clear_session()
        self.render_dashboard(clear=True)
        self.notebook.select(self.login_frame)

    def ensure_device_keypair(self) -> None:
        if self.state_store.device_private_key and self.state_store.device_public_key:
            return
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        self.state_store.device_private_key = b64u_encode(
            private_key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        )
        self.state_store.device_public_key = b64u_encode(
            public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        self.state_store.save()
        self.log("Generated local X25519 device keypair.")

    def register_device(self) -> None:
        try:
            self.ensure_device_keypair()
            payload = {
                "device_public_key": self.state_store.device_public_key,
                "device_label": "desktop-client",
                "platform": "desktop",
                "app_version": "0.1.0",
                "metadata": {"hostname_hint": secrets.token_hex(4)},
            }
            data = self._request("POST", "/client/devices/register", json_body=payload)
            self.state_store.device_id = data["device"]["id"]
            self.state_store.save()
            self.render_dashboard()
            self.log("Device registered.")
        except Exception as exc:
            messagebox.showerror("Device Registration Failed", str(exc))

    def _decrypt_envelope(self, envelope: dict) -> dict:
        private_raw = b64u_decode(self.state_store.device_private_key)
        private_key = X25519PrivateKey.from_private_bytes(private_raw)
        peer_public_key = X25519PublicKey.from_public_bytes(b64u_decode(envelope["ephemeral_public_key"]))
        shared = private_key.exchange(peer_public_key)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"onyx-client-envelope-v1").derive(shared)
        cipher = ChaCha20Poly1305(key)
        plaintext = cipher.decrypt(
            b64u_decode(envelope["nonce"]),
            b64u_decode(envelope["ciphertext"]),
            None,
        )
        return json.loads(plaintext.decode("utf-8"))

    def verify_device(self) -> None:
        try:
            if not self.state_store.device_id:
                raise RuntimeError("Device is not registered.")
            challenge = self._request("POST", "/client/devices/challenge", json_body={"device_id": self.state_store.device_id})
            decrypted = self._decrypt_envelope(challenge["envelope"])
            payload = {
                "device_id": self.state_store.device_id,
                "challenge_response": decrypted["challenge"],
            }
            self._request("POST", "/client/devices/verify", json_body=payload)
            self.log("Device challenge verified.")
        except Exception as exc:
            messagebox.showerror("Device Verify Failed", str(exc))

    def issue_bundle(self) -> None:
        try:
            if not self.state_store.device_id:
                raise RuntimeError("Device is not registered.")
            issued = self._request("POST", "/client/bundles/issue", json_body={"device_id": self.state_store.device_id})
            decrypted = self._decrypt_envelope(issued["encrypted_bundle"])
            self.state_store.last_bundle = {
                "bundle_id": issued["bundle_id"],
                "expires_at": issued["expires_at"],
                "bundle_hash": issued["bundle_hash"],
                "decrypted": decrypted,
            }
            self.state_store.save()
            self.render_dashboard()
            self.log("Bundle issued and decrypted locally.")
        except Exception as exc:
            messagebox.showerror("Bundle Issue Failed", str(exc))

    def render_dashboard(self, *, offline: bool = False, clear: bool = False) -> None:
        self.dashboard_summary.delete("1.0", "end")
        self.bundle_view.delete("1.0", "end")
        if clear:
            self.dashboard_summary.insert("end", "No active session.\n")
            self.bundle_view.insert("end", "No bundle.\n")
            return
        user = self.state_store.user or {}
        subscription = self.state_store.subscription or {}
        summary = {
            "offline_cached_session": offline,
            "base_url": self.state_store.base_url,
            "username": user.get("username"),
            "email": user.get("email"),
            "user_status": user.get("status"),
            "device_id": self.state_store.device_id or None,
            "subscription_id": subscription.get("id"),
            "subscription_expires_at": subscription.get("expires_at"),
            "bundle_expires_at": (self.state_store.last_bundle or {}).get("expires_at"),
        }
        self.dashboard_summary.insert("end", json.dumps(summary, indent=2, ensure_ascii=False))
        if self.state_store.last_bundle:
            self.bundle_view.insert("end", json.dumps(self.state_store.last_bundle["decrypted"], indent=2, ensure_ascii=False))
        else:
            self.bundle_view.insert("end", "No bundle issued yet.\n")


if __name__ == "__main__":
    app = ONyXDesktopClient()
    app.mainloop()
