"""
DNS-based SID lookup against the sid.yt tree.

Resolution logic:
  1. Convert SID to reversed 20-digit label, detect zone
  2. TXT record → module fully registered (key=value fields)
     If TXT contains entry_point=N, follow up on N for module-level info
  3. PTR record → entry-point known, module not yet detailed
  4. No answer → SID not registered
"""

import subprocess
import logging
import json
import urllib.request

_logger = logging.getLogger(__name__)

KNOWN_ZONES = [
    (0,               999_999,           "ietf.sid.yt",                   False),
    (5_000_000,       5_999_999,         "afnic.sid.yt",                  False),
    (3_000_000_000,   3_999_999_999,     "3.0.0.0.0.0.0.0.0.0.0.sid.yt", True),
    (300_000_000_000, 399_999_999_999,   "3.0.0.0.0.0.0.0.0.sid.yt",     True),
]


def reversed_name(sid: int) -> str:
    return ".".join(reversed(f"{sid:020d}"))


def detect_zone(sid: int) -> tuple[str | None, bool]:
    for lo, hi, zone, numeric in KNOWN_ZONES:
        if lo <= sid <= hi:
            return zone, numeric
    return None, False


def make_fqdn(sid: int, zone: str, numeric: bool) -> str:
    rev = reversed_name(sid)
    if numeric:
        return f"{rev}.sid.yt"
    return f"{rev}.{zone}"


def _dig(fqdn: str, rtype: str) -> list[str]:
    try:
        result = subprocess.run(
            ["dig", "+noall", "+answer", fqdn, rtype],
            capture_output=True, text=True, timeout=5,
        )
        return [l for l in result.stdout.splitlines() if l and not l.startswith(";")]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        _logger.warning("dig unavailable or timed out for %s %s", fqdn, rtype)
        return []


def _parse_txt_fields(records: list[str]) -> dict[str, str]:
    fields = {}
    for r in records:
        for part in r.split('"'):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                fields[k.strip()] = v.strip()
    return fields


def query_sid(sid: int) -> dict:
    """
    Query the sid.yt DNS tree for a SID.

    Returns a dict with keys:
      - status: "registered" | "entry-point-only" | "not-registered" | "unknown-zone"
      - fields: dict of key=value info from TXT records (may be empty)
      - fqdn: the DNS name queried (or None)
    """
    zone, numeric = detect_zone(sid)
    if zone is None:
        return {"status": "unknown-zone", "fields": {}, "fqdn": None}

    fqdn = make_fqdn(sid, zone, numeric)
    _logger.debug("Querying TXT %s for SID %d", fqdn, sid)

    txt = _dig(fqdn, "TXT")
    if txt:
        fields = _parse_txt_fields(txt)
        if "entry_point" in fields:
            ep = int(fields["entry_point"])
            ep_zone, ep_numeric = detect_zone(ep)
            if ep_zone:
                ep_fqdn = make_fqdn(ep, ep_zone, ep_numeric)
                ep_fields = _parse_txt_fields(_dig(ep_fqdn, "TXT"))
                fields = {**ep_fields, **fields}
        return {"status": "registered", "fields": fields, "fqdn": fqdn}

    ptr = _dig(fqdn, "PTR")
    if ptr:
        return {"status": "entry-point-only", "fields": {}, "fqdn": fqdn}

    return {"status": "not-registered", "fields": {}, "fqdn": fqdn}


def fetch_sid_file(url: str) -> dict | None:
    """Download a .sid file from url and return its parsed JSON, or None on error."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        _logger.error("Failed to fetch SID file from %s: %s", url, e)
        return None
