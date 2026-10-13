"""Synthetic security cases: no request is sent to a real private service."""
import socket
from unittest.mock import Mock

import httpx
import pytest

from agent_read import killchain
from agent_read.safety import is_safe_url


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, port, *a, **k:
                        [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))])


@pytest.mark.parametrize('target', ['http://127.0.0.1/private', 'http://169.254.169.254/',
                                   'http://100.64.0.1/', 'http://224.0.0.1/', 'http://[::1]/'])
def test_redirect_cannot_reach_nonpublic_address(target):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'location': target})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ValueError):
            killchain._fetch(client, 'https://example.com/start', 0)
    assert seen == ['https://example.com/start']


def test_relative_public_redirect_succeeds():
    def handler(request):
        if request.url.path == '/start':
            return httpx.Response(302, headers={'location': '/article'})
        return httpx.Response(200, text='article')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = killchain._fetch(client, 'https://example.com/start', 0)
    assert response.text == 'article'
    assert str(response.url) == 'https://example.com/article'


def test_dns_failure_is_denied(monkeypatch):
    def fail(*a, **k):
        raise socket.gaierror('unresolved')
    monkeypatch.setattr(socket, 'getaddrinfo', fail)
    assert is_safe_url('https://unresolved.example')[0] is False


def test_mixed_dns_is_denied(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
        for ip in ['93.184.216.34', '127.0.0.1']])
    assert is_safe_url('https://mixed.example')[0] is False


def test_connection_uses_validated_ip_and_rejects_later_rebinding():
    from agent_read.fetch import PublicNetworkBackend
    backend = Mock()
    answers = iter(['93.184.216.34', '127.0.0.1'])
    def resolve(host, port, *a):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (next(answers), port))]
    protected = PublicNetworkBackend(backend=backend, resolver=resolve)
    protected.connect_tcp('example.com', 443)
    assert backend.connect_tcp.call_args.args[:2] == ('93.184.216.34', 443)
    with pytest.raises(ValueError):
        protected.connect_tcp('example.com', 443)
    assert backend.connect_tcp.call_count == 1


def test_youtube_does_not_launch_unprotected_downloader_by_default(monkeypatch):
    downloader = Mock(return_value='synthetic transcript ' * 30)
    monkeypatch.setattr(killchain, '_strategy_youtube', downloader)
    result = killchain.read('https://www.youtube.com/watch?v=example')
    downloader.assert_not_called()
    assert not result.ok
    assert 'external downloader' in result.error


def test_youtube_lookalike_is_not_special_cased():
    assert not killchain._is_youtube('https://notyoutube.com/watch?v=example')
    assert killchain._is_youtube('https://www.youtube.com/watch?v=example')


def test_redirect_loop_is_bounded():
    from agent_read.fetch import safe_get
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'location': '/again'})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ValueError, match='Too many redirects'):
            safe_get(client, 'https://example.com/start', max_redirects=2)
    assert len(seen) == 3


@pytest.mark.parametrize('declared', [None, '100000', 'invalid'])
def test_body_limits_and_invalid_length_fail(declared):
    from agent_read.fetch import safe_get
    headers = {'content-length': declared} if declared else {}
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, content=b'x' * 128))) as client:
        with pytest.raises(ValueError):
            safe_get(client, 'https://example.com/page', max_bytes=32)


def test_wayback_redirects_use_the_same_policy():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if '/cdx/' in request.url.path:
            return httpx.Response(200, json=[['urlkey', 'timestamp'], ['example.com', '20260101000000']])
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/internal'})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ValueError):
            killchain._strategy_wayback(client, 'https://example.com/page?a=1&b=2', 1000)
    assert len(seen) == 2
    assert 'url=https%3A%2F%2Fexample.com%2Fpage%3Fa%3D1%26b%3D2' in seen[0]
    assert all('127.0.0.1' not in url for url in seen)


def test_batch_uses_protected_read_without_injected_plain_client(monkeypatch):
    from agent_read.cli import _read_all
    observed = []
    def fake_read(url, **kwargs):
        observed.append(kwargs)
        return killchain.ReadResult(url, ok=False)
    monkeypatch.setattr('agent_read.cli.read', fake_read)
    _read_all(['https://example.com/a', 'https://example.com/b'], 500)
    assert len(observed) == 2
    assert all('client' not in kwargs for kwargs in observed)


def test_youtube_explicit_opt_in_still_calls_downloader(monkeypatch):
    downloader = Mock(return_value='synthetic transcript ' * 30)
    monkeypatch.setattr(killchain, '_strategy_youtube', downloader)
    result = killchain.read('https://www.youtube.com/watch?v=example', allow_external_downloader=True)
    assert result.ok
    downloader.assert_called_once()


def test_default_client_ignores_proxy_environment(monkeypatch):
    from agent_read.fetch import public_client, PublicTransport
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    with public_client() as client:
        assert isinstance(client._transport_for_url(httpx.URL('https://example.com')), PublicTransport)
