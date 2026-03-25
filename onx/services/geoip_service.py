"""GeoIP service — fetches country CIDR lists and computes split-tunnel AllowedIPs."""
from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

import httpx

log = logging.getLogger(__name__)

IPDENY_URL = "https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone"


@lru_cache(maxsize=64)
def fetch_country_cidrs(country_code: str) -> list[str]:
    """Fetch IPv4 CIDR list for *country_code* (ISO 3166-1 alpha-2, lowercase)."""
    url = IPDENY_URL.format(country=country_code.lower())
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip() and not line.startswith("#")]


def compute_excluded_allowed_ips(country_code: str) -> list[str]:
    """Return AllowedIPs that route everything EXCEPT the country's IPs through the tunnel.

    The result is a list of IPv4 CIDRs covering the complement of the country's
    address space, plus '::/0' to tunnel all IPv6 traffic.
    """
    try:
        country_cidrs = fetch_country_cidrs(country_code.lower())
    except Exception as exc:
        log.warning("GeoIP: failed to fetch CIDRs for %r: %s", country_code, exc)
        return ["0.0.0.0/0", "::/0"]

    remaining: list[ipaddress.IPv4Network] = [ipaddress.ip_network("0.0.0.0/0")]

    for raw in country_cidrs:
        try:
            exclude = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if exclude.version != 4:
            continue
        new_remaining: list[ipaddress.IPv4Network] = []
        for net in remaining:
            if net.overlaps(exclude):
                try:
                    new_remaining.extend(net.address_exclude(exclude))
                except ValueError:
                    new_remaining.append(net)
            else:
                new_remaining.append(net)
        remaining = new_remaining

    collapsed = list(ipaddress.collapse_addresses(remaining))
    result = [str(net) for net in collapsed]
    result.append("::/0")
    return result
