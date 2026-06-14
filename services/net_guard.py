"""Network safety helpers — guard against SSRF on user-supplied URLs.

``/api/read`` fetches an arbitrary URL on behalf of the client. Without a
guard, a caller could point it at internal addresses (cloud metadata at
``169.254.169.254``, ``localhost`` admin panels, private LAN hosts) and turn
the server into a probe/proxy. :func:`is_safe_public_url` rejects anything that
is not a plain http(s) URL resolving exclusively to public IP addresses.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # Reject loopback, private (RFC1918), link-local (incl. cloud metadata
    # 169.254.169.254), multicast, reserved, and unspecified ranges.
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def is_safe_public_url(url: str) -> bool:
    """Return True only for http(s) URLs whose host resolves to public IPs.

    All addresses the hostname resolves to must be public — a single private
    result is enough to reject, which also blunts DNS-rebinding tricks where a
    name returns both a public and an internal address.
    """

    if not url or not isinstance(url, str):
        return False

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False

    host = parsed.hostname
    if not host:
        return False

    # A literal IP host is checked directly; a name is resolved to every IP.
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return False

    resolved = {info[4][0] for info in infos}
    if not resolved:
        return False
    return all(_ip_is_public(ip) for ip in resolved)
