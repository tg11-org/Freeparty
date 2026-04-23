from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

from django.conf import settings


BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata.internal"}
ALLOWED_URL_SCHEMES = {"http", "https"}


class UnsafeRemoteURL(ValueError):
    """Raised when a remote fetch target is not safe to request."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(req.full_url, code, f"Redirect blocked to {newurl}", headers, fp)


def normalize_hostname(hostname: str | None) -> str:
    return (hostname or "").strip().lower().rstrip(".")


def validate_remote_url(url: str, *, allowed_domain: str | None = None, allow_http: bool = True) -> None:
    parsed = urlparse(url)
    allowed_schemes = ALLOWED_URL_SCHEMES if allow_http else {"https"}
    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeRemoteURL("Remote URL scheme is not allowed.")

    host = normalize_hostname(parsed.hostname)
    if not host or host in BLOCKED_HOSTS:
        raise UnsafeRemoteURL("Remote URL host is not allowed.")

    if allowed_domain is not None and host != normalize_hostname(allowed_domain):
        raise UnsafeRemoteURL("Remote URL host does not match the expected domain.")

    for address in resolve_all_addresses(host):
        if is_private_or_reserved_address(address):
            raise UnsafeRemoteURL("Remote URL resolves to a private or reserved address.")


def resolve_all_addresses(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    if getattr(settings, "TESTING", False) and host.endswith(".example"):
        return {ipaddress.ip_address("93.184.216.34")}

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeRemoteURL("Remote URL host could not be resolved.") from exc

    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses:
        raise UnsafeRemoteURL("Remote URL host resolved to no addresses.")
    return addresses


def is_private_or_reserved_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def safe_urlopen(
    request: urllib.request.Request | str,
    *,
    timeout: int,
    allowed_domain: str | None = None,
    allow_http: bool = True,
    allow_redirects: bool = False,
):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    validate_remote_url(url, allowed_domain=allowed_domain, allow_http=allow_http)

    if allow_redirects:
        response = urllib.request.urlopen(request, timeout=timeout)  # nosec B310 - URL validated before and after open.
        final_url = response.geturl() if hasattr(response, "geturl") else url
        validate_remote_url(final_url, allowed_domain=allowed_domain, allow_http=allow_http)
        return response

    opener = urllib.request.build_opener(NoRedirectHandler)
    return opener.open(request, timeout=timeout)
