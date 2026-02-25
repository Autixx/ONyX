import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime

from modules.Utilities import ValidateDNSAddress


class OutboundProfiles:
    AWG_KEYS = {"Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"}
    BALANCER_METHODS = {"random", "leastload", "leastping"}
    HANDSHAKE_ONLINE_WINDOW_SEC = 180

    def __init__(self, DashboardConfig):
        self.DashboardConfig = DashboardConfig
        self.configuration_path = os.getenv("CONFIGURATION_PATH", ".")
        self.outbound_path = os.path.join(self.configuration_path, "outbound")
        self.protocol_paths = {
            "wg": os.path.join(self.outbound_path, "wg"),
            "awg": os.path.join(self.outbound_path, "awg")
        }
        self.settings_path = os.path.join(self.outbound_path, "settings.json")
        self._ensure_structure()

    def _ensure_structure(self):
        os.makedirs(self.outbound_path, exist_ok=True)
        for path in self.protocol_paths.values():
            os.makedirs(path, exist_ok=True)

        if not os.path.exists(self.settings_path):
            self._write_settings(self._default_settings())
        else:
            settings = self._read_settings()
            self._write_settings(settings)

    def _default_settings(self):
        return {
            "Balancers": {
                "Method": "random",
                "Profiles": []
            },
            "DNSSettings": {
                "LocalDNSInstalled": False,
                "LocalDNSAddress": ""
            },
            "SiteToSite": {
                "Enabled": False,
                "NextProfile": ""
            },
            "Multihop": {
                "Profiles": []
            }
        }

    def _read_settings(self):
        default = self._default_settings()
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return default

        if not isinstance(raw, dict):
            return default

        settings = default
        settings["Balancers"]["Method"] = str(
            raw.get("Balancers", {}).get("Method", default["Balancers"]["Method"])
        ).lower()
        settings["Balancers"]["Profiles"] = list(raw.get("Balancers", {}).get("Profiles", []))
        settings["DNSSettings"]["LocalDNSInstalled"] = bool(
            raw.get("DNSSettings", {}).get("LocalDNSInstalled", False)
        )
        settings["DNSSettings"]["LocalDNSAddress"] = str(
            raw.get("DNSSettings", {}).get("LocalDNSAddress", "")
        ).strip()
        settings["SiteToSite"]["Enabled"] = bool(
            raw.get("SiteToSite", {}).get("Enabled", False)
        )
        settings["SiteToSite"]["NextProfile"] = str(
            raw.get("SiteToSite", {}).get("NextProfile", "")
        ).strip()
        settings["Multihop"]["Profiles"] = list(raw.get("Multihop", {}).get("Profiles", []))

        if settings["Balancers"]["Method"] not in self.BALANCER_METHODS:
            settings["Balancers"]["Method"] = default["Balancers"]["Method"]
        return settings

    def _write_settings(self, settings):
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=True)

    def _sanitize_profile_name(self, name):
        name = str(name).strip()
        if re.match(r"^[A-Za-z0-9_=+.-]{1,15}$", name) is None:
            return False, "Invalid profile name. Allowed chars: A-Z, a-z, 0-9, _ = + . - (max 15)."
        return True, name

    def _profile_path(self, protocol, name):
        return os.path.join(self.protocol_paths[protocol], f"{name}.conf")

    def _list_profile_names(self):
        names = set()
        for protocol, path in self.protocol_paths.items():
            if not os.path.isdir(path):
                continue
            for file_name in os.listdir(path):
                if file_name.endswith(".conf"):
                    names.add((file_name[:-5], protocol))
        return names

    def _profile_exists(self, name):
        for protocol in self.protocol_paths.keys():
            if os.path.exists(self._profile_path(protocol, name)):
                return True
        return False

    def _find_profile(self, name):
        for protocol in self.protocol_paths.keys():
            path = self._profile_path(protocol, name)
            if os.path.exists(path):
                return {"Name": name, "Protocol": protocol, "Path": path}
        return None

    def _inbound_profile_exists(self, name):
        for protocol in ["wg", "awg"]:
            _, conf_path = self.DashboardConfig.GetConfig("Server", f"{protocol}_conf_path")
            if os.path.exists(os.path.join(conf_path, f"{name}.conf")):
                return True
        return False

    def _detect_protocol(self, content, fallback="wg"):
        try:
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if line == "[Peer]":
                    break
                if not line or line == "[Interface]" or line.startswith("#") or line.startswith(";"):
                    continue
                key_value = re.split(r"\s*=\s*", line, 1)
                if len(key_value) == 2 and key_value[0] in self.AWG_KEYS:
                    return "awg"
        except Exception:
            return fallback
        return fallback

    def _quick_binary(self, protocol):
        return f"{protocol}-quick"

    def _interface_running(self, profile_name):
        try:
            result = subprocess.run(
                ["ip", "link", "show", "dev", profile_name],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run(self, cmd):
        try:
            process = subprocess.run(cmd, capture_output=True, text=True)
            ok = process.returncode == 0
            msg = process.stderr.strip() if not ok else process.stdout.strip()
            return ok, msg
        except Exception as e:
            return False, str(e)

    def _get_latest_handshake(self, protocol, profile_name):
        binary = shutil.which(protocol)
        if binary is None:
            return None
        ok, output = self._run([binary, "show", profile_name, "latest-handshakes"])
        if not ok:
            return None
        latest = 0
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                value = int(parts[1])
                if value > latest:
                    latest = value
            except Exception:
                continue
        return latest if latest > 0 else None

    def _get_transfer(self, protocol, profile_name):
        binary = shutil.which(protocol)
        if binary is None:
            return 0.0, 0.0, 0.0
        ok, output = self._run([binary, "show", profile_name, "transfer"])
        if not ok:
            return 0.0, 0.0, 0.0
        rx = 0
        tx = 0
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                rx += int(parts[1])
                tx += int(parts[2])
            except Exception:
                continue
        gb = 1024.0 * 1024.0 * 1024.0
        r = rx / gb
        s = tx / gb
        return r, s, (r + s)

    def _profile_runtime(self, protocol, profile_name):
        status = self._interface_running(profile_name)
        latest_handshake = self._get_latest_handshake(protocol, profile_name) if status else None
        receive, sent, total = self._get_transfer(protocol, profile_name) if status else (0.0, 0.0, 0.0)

        availability = "offline"
        if status:
            if latest_handshake is not None:
                if int(time.time()) - latest_handshake <= self.HANDSHAKE_ONLINE_WINDOW_SEC:
                    availability = "online"
                else:
                    availability = "stale"
            else:
                availability = "up"

        latest_handshake_text = None
        if latest_handshake is not None:
            latest_handshake_text = datetime.fromtimestamp(latest_handshake).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "Status": status,
            "Availability": availability,
            "LatestHandshake": latest_handshake,
            "LatestHandshakeAt": latest_handshake_text,
            "DataUsage": {
                "Receive": receive,
                "Sent": sent,
                "Total": total
            }
        }

    def _clean_settings_references(self, settings):
        existing_names = {name for name, _ in self._list_profile_names()}

        settings["Balancers"]["Profiles"] = [
            n for n in settings["Balancers"]["Profiles"] if n in existing_names
        ]
        settings["Multihop"]["Profiles"] = [
            n for n in settings["Multihop"]["Profiles"] if n in existing_names
        ]

        if settings["SiteToSite"]["NextProfile"] not in existing_names:
            settings["SiteToSite"]["Enabled"] = False
            settings["SiteToSite"]["NextProfile"] = ""

        if not settings["DNSSettings"]["LocalDNSInstalled"]:
            settings["DNSSettings"]["LocalDNSAddress"] = ""

        return settings

    def listProfiles(self):
        profiles = []
        entries = list(self._list_profile_names())
        entries.sort(key=lambda x: x[0].lower())
        for name, protocol in entries:
            path = self._profile_path(protocol, name)
            runtime = self._profile_runtime(protocol, name)
            profiles.append({
                "Name": name,
                "Protocol": protocol,
                "Path": path,
                **runtime
            })
        return profiles

    def getAllData(self):
        settings = self._read_settings()
        settings = self._clean_settings_references(settings)
        self._write_settings(settings)
        return {
            "Profiles": self.listProfiles(),
            "Settings": settings
        }

    def importProfile(self, data):
        if not isinstance(data, dict):
            return False, "Please provide request body."

        valid_name, name = self._sanitize_profile_name(data.get("Name"))
        if not valid_name:
            return False, name

        content = str(data.get("Content", "")).strip()
        if len(content) == 0:
            return False, "Please provide profile content."

        if self._profile_exists(name):
            return False, "Profile already exists."
        if self._inbound_profile_exists(name):
            return False, "Profile name conflicts with an inbound configuration."

        protocol_input = str(data.get("Protocol", "auto")).strip().lower()
        if protocol_input in ["wg", "awg"]:
            protocol = protocol_input
        else:
            protocol = self._detect_protocol(content, fallback="wg")

        file_path = self._profile_path(protocol, name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))

        settings = self._read_settings()
        if name not in settings["Multihop"]["Profiles"]:
            settings["Multihop"]["Profiles"].append(name)
        settings = self._clean_settings_references(settings)
        self._write_settings(settings)
        return True, "Profile imported."

    def toggleProfile(self, name):
        profile = self._find_profile(name)
        if profile is None:
            return False, "Profile does not exist.", None

        protocol = profile["Protocol"]
        quick = shutil.which(self._quick_binary(protocol))
        if quick is None:
            return False, f"{protocol}-quick is not installed.", None

        running = self._interface_running(name)
        command = [quick, "down", profile["Path"]] if running else [quick, "up", profile["Path"]]
        status, msg = self._run(command)
        new_status = self._interface_running(name)
        if status:
            return True, None, new_status
        return False, (msg if msg else "Failed to toggle profile."), new_status

    def deleteProfile(self, name):
        profile = self._find_profile(name)
        if profile is None:
            return False, "Profile does not exist."

        if self._interface_running(name):
            status, msg, _ = self.toggleProfile(name)
            if not status:
                return False, msg if msg else "Cannot stop profile before deleting."

        try:
            os.remove(profile["Path"])
        except Exception as e:
            return False, str(e)

        settings = self._read_settings()
        settings["Balancers"]["Profiles"] = [x for x in settings["Balancers"]["Profiles"] if x != name]
        settings["Multihop"]["Profiles"] = [x for x in settings["Multihop"]["Profiles"] if x != name]
        if settings["SiteToSite"]["NextProfile"] == name:
            settings["SiteToSite"]["Enabled"] = False
            settings["SiteToSite"]["NextProfile"] = ""
        settings = self._clean_settings_references(settings)
        self._write_settings(settings)
        return True, "Profile deleted."

    def getRawProfile(self, name):
        profile = self._find_profile(name)
        if profile is None:
            return False, "Profile does not exist.", None
        with open(profile["Path"], "r", encoding="utf-8") as f:
            return True, None, {
                "Name": profile["Name"],
                "Protocol": profile["Protocol"],
                "Path": profile["Path"],
                "Content": f.read()
            }

    def updateRawProfile(self, name, content):
        profile = self._find_profile(name)
        if profile is None:
            return False, "Profile does not exist."
        if content is None or len(str(content)) == 0:
            return False, "Please provide profile content."

        current = ""
        with open(profile["Path"], "r", encoding="utf-8") as f:
            current = f.read()

        was_running = self._interface_running(name)
        if was_running:
            status, msg, _ = self.toggleProfile(name)
            if not status:
                return False, msg if msg else "Cannot stop profile."

        try:
            with open(profile["Path"], "w", encoding="utf-8") as f:
                f.write(str(content))
        except Exception as e:
            if was_running:
                self.toggleProfile(name)
            return False, str(e)

        if was_running:
            status, msg, _ = self.toggleProfile(name)
            if not status:
                with open(profile["Path"], "w", encoding="utf-8") as f:
                    f.write(current)
                self.toggleProfile(name)
                return False, msg if msg else "Failed to start profile with updated config."
        return True, "Profile updated."

    def updateSettings(self, data):
        if not isinstance(data, dict):
            return False, "Please provide request body."

        settings = self._read_settings()
        profile_names = {name for name, _ in self._list_profile_names()}

        if "Balancers" in data:
            balancer = data.get("Balancers", {})
            method = str(balancer.get("Method", settings["Balancers"]["Method"])).lower()
            profiles = balancer.get("Profiles", settings["Balancers"]["Profiles"])

            if method not in self.BALANCER_METHODS:
                return False, "Unsupported balancer method."
            if not isinstance(profiles, list):
                return False, "Balancer profiles must be a list."

            cleaned = []
            for profile in profiles:
                profile_name = str(profile).strip()
                if profile_name not in profile_names:
                    return False, f"Profile does not exist: {profile_name}"
                if profile_name not in cleaned:
                    cleaned.append(profile_name)

            settings["Balancers"]["Method"] = method
            settings["Balancers"]["Profiles"] = cleaned

        if "DNSSettings" in data:
            dns_settings = data.get("DNSSettings", {})
            installed = bool(dns_settings.get(
                "LocalDNSInstalled",
                settings["DNSSettings"]["LocalDNSInstalled"]
            ))
            address = str(dns_settings.get(
                "LocalDNSAddress",
                settings["DNSSettings"]["LocalDNSAddress"]
            )).strip()

            if installed:
                if len(address) == 0:
                    return False, "Please provide local DNS address."
                valid_dns, dns_message = ValidateDNSAddress(address)
                if not valid_dns:
                    return False, dns_message
            else:
                address = ""

            settings["DNSSettings"]["LocalDNSInstalled"] = installed
            settings["DNSSettings"]["LocalDNSAddress"] = address

        if "SiteToSite" in data:
            site_to_site = data.get("SiteToSite", {})
            enabled = bool(site_to_site.get("Enabled", settings["SiteToSite"]["Enabled"]))
            next_profile = str(site_to_site.get("NextProfile", settings["SiteToSite"]["NextProfile"])).strip()

            if enabled and len(next_profile) == 0:
                return False, "Please select next profile."
            if next_profile and next_profile not in profile_names:
                return False, "Site-to-site profile does not exist."

            settings["SiteToSite"]["Enabled"] = enabled
            settings["SiteToSite"]["NextProfile"] = next_profile

        if "Multihop" in data:
            multihop = data.get("Multihop", {})
            profiles = multihop.get("Profiles", settings["Multihop"]["Profiles"])
            if not isinstance(profiles, list):
                return False, "Multihop profiles must be a list."

            cleaned = []
            for profile in profiles:
                profile_name = str(profile).strip()
                if profile_name not in profile_names:
                    return False, f"Profile does not exist: {profile_name}"
                if profile_name not in cleaned:
                    cleaned.append(profile_name)
            settings["Multihop"]["Profiles"] = cleaned

        settings = self._clean_settings_references(settings)
        self._write_settings(settings)
        return True, "Settings updated."
