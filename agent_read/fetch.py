"""Public-only HTTP transport and bounded, explicitly checked redirects.

HTTPX transport API and HTTPCore's network_backend extension preserve the
original Host header and TLS hostname while connecting to a validated IP.
Environment proxies are intentionally not inherited.
"""
from __future__ import annotations

from urllib.parse import urljoin

import httpcore
import httpx

from .safety import UnsafeURL, is_safe_url, public_addresses

MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5


class PublicNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, backend=None, resolver=None):
        self.backend = backend or httpcore.SyncBackend()
        self.resolver = resolver

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = public_addresses(host, port, resolver=self.resolver)
        last_error = None
        for address in addresses:
            try:
                return self.backend.connect_tcp(address, port, timeout=timeout,
                    local_address=local_address, socket_options=socket_options)
            except (OSError, httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise UnsafeURL('Unix sockets are not supported')


class _Stream(httpx.SyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        try:
            yield from self.stream
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError) as exc:
            raise httpx.TransportError(str(exc)) from exc

    def close(self):
        self.stream.close()


class PublicTransport(httpx.BaseTransport):
    def __init__(self):
        self.pool = httpcore.ConnectionPool(network_backend=PublicNetworkBackend(),
                                           max_connections=5, max_keepalive_connections=5)

    def handle_request(self, request):
        req = httpcore.Request(method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host,
                             port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw, content=request.stream, extensions=request.extensions)
        try:
            response = self.pool.handle_request(req)
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError) as exc:
            raise httpx.TransportError(str(exc)) from exc
        return httpx.Response(response.status, headers=response.headers,
                              stream=_Stream(response.stream), extensions=response.extensions)

    def close(self):
        self.pool.close()


def public_client() -> httpx.Client:
    return httpx.Client(transport=PublicTransport(), trust_env=False,
                        follow_redirects=False, timeout=15.0)


def safe_get(client: httpx.Client, url: str, *, max_bytes=MAX_BYTES,
             max_redirects=MAX_REDIRECTS, **kwargs) -> httpx.Response:
    """Validate each target, never auto-follow, and cap the decoded body.

    An explicitly supplied client is a trusted dependency: callers must supply
    PublicTransport (or a network-isolated test transport) for DNS pinning.
    """
    current = url
    for hop in range(max_redirects + 1):
        allowed, reason = is_safe_url(current)
        if not allowed:
            raise UnsafeURL(reason)
        # Build a new request per hop. Do not carry query params across redirects.
        request = client.build_request('GET', current, **kwargs)
        response = client.send(request, stream=True, follow_redirects=False)
        try:
            if response.has_redirect_location:
                if hop == max_redirects:
                    raise UnsafeURL('Too many redirects')
                current = urljoin(str(response.url), response.headers['location'])
                kwargs.pop('params', None)
                continue
            declared = response.headers.get('content-length')
            if declared is not None and (int(declared) < 0 or int(declared) > max_bytes):
                raise ValueError('Response size exceeds limit or is invalid')
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > max_bytes:
                    raise ValueError('Response size exceeds limit')
                body.extend(chunk)
            # The body is already decoded; avoid a second content-decoding pass.
            headers = [(k, v) for k, v in response.headers.multi_items()
                       if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')]
            return httpx.Response(response.status_code, headers=headers, content=bytes(body),
                                  request=request, extensions=response.extensions)
        finally:
            response.close()
    raise UnsafeURL('Too many redirects')
