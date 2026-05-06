from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

import httpx
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


def validate_url_structure(url: str, *, allowed_domain: str | None = None, allow_http: bool = True) -> None:
    """Validate URL scheme, host format, and domain allowlist — without DNS resolution."""
    parsed = urlparse(url)
    allowed_schemes = ALLOWED_URL_SCHEMES if allow_http else {"https"}
    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeRemoteURL("Remote URL scheme is not allowed.")

    host = normalize_hostname(parsed.hostname)
    if not host or host in BLOCKED_HOSTS:
        raise UnsafeRemoteURL("Remote URL host is not allowed.")

    if allowed_domain is not None and host != normalize_hostname(allowed_domain):
        raise UnsafeRemoteURL("Remote URL host does not match the expected domain.")


def validate_remote_url(url: str, *, allowed_domain: str | None = None, allow_http: bool = True) -> None:
    """Validate URL structure and all DNS-resolved addresses."""
    validate_url_structure(url, allowed_domain=allowed_domain, allow_http=allow_http)
    parsed = urlparse(url)
    host = normalize_hostname(parsed.hostname)
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


class PinnedIPTransport(httpx.HTTPTransport):
    """
    httpx transport that resolves the target hostname once, validates every
    returned address against private/reserved ranges, then pins the TCP
    connection to that exact IP — eliminating the DNS re-resolution window
    that enables DNS-rebinding SSRF attacks (FP-007).

    The original hostname is preserved as the HTTP Host header and TLS SNI
    value so that HTTP/1.1 virtual-hosting and certificate validation work
    correctly against the IP-addressed connection.
    """

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host

        # 1. Resolve hostname and validate every address.
        addresses = resolve_all_addresses(host)
        for addr in addresses:
            if is_private_or_reserved_address(addr):
                raise UnsafeRemoteURL(
                    f"Host {host!r} resolves to a private or reserved address."
                )

        # 2. Pin to one validated IP (prefer IPv4 for wider server compatibility).
        ipv4 = [a for a in addresses if isinstance(a, ipaddress.IPv4Address)]
        pinned_ip = str(ipv4[0] if ipv4 else next(iter(addresses)))
        url_host = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip

        # 3. Rewrite the request URL to the pinned IP so httpcore connects
        #    to exactly the address we validated without a second OS lookup.
        pinned_url = request.url.copy_with(host=url_host)

        # 4. Restore the original Host header (HTTP/1.1 requirement) and pass
        #    the original hostname as the TLS SNI value so certificate
        #    validation succeeds against the IP-addressed connection.
        extensions = {**request.extensions, "sni_hostname": host.encode("idna")}
        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers={**dict(request.headers), "host": host},
            content=request.content,
            extensions=extensions,
        )
        return super().handle_request(pinned_request)


def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
    timeout: int = 10,
    allowed_domain: str | None = None,
    allow_http: bool = True,
) -> httpx.Response:
    """
    Fetch a remote URL with IP-pinned transport to prevent DNS-rebinding SSRF.

    DNS is resolved exactly once inside PinnedIPTransport and the resulting
    IP is pinned for the actual TCP connection, closing the re-resolution gap
    present in safe_urlopen.  Redirects are never followed.

    Raises UnsafeRemoteURL for unsafe targets.
    Raises httpx.TimeoutException / httpx.RequestError on transport failures.
    """
    validate_url_structure(url, allowed_domain=allowed_domain, allow_http=allow_http)
    with httpx.Client(transport=PinnedIPTransport(), follow_redirects=False) as client:
        return client.request(
            method=method,
            url=url,
            headers=headers or {},
            content=content,
            timeout=timeout,
        )


def safe_urlopen(
    request: urllib.request.Request | str,
    *,
    timeout: int,
    allowed_domain: str | None = None,
    allow_http: bool = True,
    allow_redirects: bool = False,
):
    """Legacy urllib-based fetch. Prefer safe_fetch for new code."""
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    validate_remote_url(url, allowed_domain=allowed_domain, allow_http=allow_http)

    if allow_redirects:
        response = urllib.request.urlopen(request, timeout=timeout)  # nosec B310 - URL validated before and after open.
        final_url = response.geturl() if hasattr(response, "geturl") else url
        validate_remote_url(final_url, allowed_domain=allowed_domain, allow_http=allow_http)
        return response

    opener = urllib.request.build_opener(NoRedirectHandler)
    return opener.open(request, timeout=timeout)
