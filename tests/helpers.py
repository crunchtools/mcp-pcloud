"""Real httpx plumbing shared by tool tests.

The suite used to patch `httpx.AsyncClient.get`, which mocked away the thing
under test: the agent string, the response ceiling and the error detail all
live in the client's own send path, so a mock standing in for `get` could not
see any of them. `send` is scripted instead, with `build_request` left real so
the url and params assertions still read what the caller actually asked for.

The client's own behaviour -- the header it adds, the bounded read it performs
-- is tested in `test_http_contract.py` over a `MockTransport`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs

import httpx


def mock_response(payload: dict[str, Any], status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying a JSON payload."""
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("GET", "https://api.pcloud.com/test"),
    )


def text_response(body: str, status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying a plain-text body."""
    return httpx.Response(
        status_code=status_code,
        text=body,
        request=httpx.Request("GET", "https://api.pcloud.com/test"),
    )


def path_of(call: Any) -> str:
    """The path a recorded request asked for, e.g. `/listfolder`."""
    return str(sent_request(call).url.path)


def params_of(call: Any) -> dict[str, str]:
    """The query parameters of a recorded request."""
    return dict(sent_request(call).url.params)


def sent_request(call: Any) -> httpx.Request:
    """The request a recorded `send` call carried."""
    return cast_request(call.args[0])


def cast_request(value: Any) -> httpx.Request:
    """Narrow a recorded positional argument to the request it is."""
    assert isinstance(value, httpx.Request)
    return value


@contextmanager
def patch_client(*responses: httpx.Response) -> Iterator[MagicMock]:
    """Script `httpx.AsyncClient.send` with the given responses, in order.

    Hands back the `send` mock, so a test can count the requests a tool made
    and read each one off the real `httpx.Request` that was sent.
    """
    mock_send = AsyncMock(side_effect=list(responses))
    with patch.object(httpx.AsyncClient, "send", mock_send):
        yield mock_send


@contextmanager
def patch_token_exchange(
    payload: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    side_effect: Exception | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Put a MockTransport under the sync client the token exchange creates.

    The exchange streams now, so a patch on `httpx.Client.post` would not be
    reached -- and could not see the agent string or the response ceiling in
    any case, since both belong to the client rather than to the call. The
    client is still constructed by production code, which is the point: a test
    of the header it sets has to let it set one.

    What comes back is the request that actually went out: its URL, its form
    (decoded from the wire, so a secret that leaked into the query string
    cannot hide in it) and its headers.
    """
    captured: dict[str, Any] = {}
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["data"] = {
            key: values[0] for key, values in parse_qs(request.content.decode()).items()
        }
        captured["headers"] = dict(request.headers)
        if side_effect is not None:
            raise side_effect
        if content is not None:
            return httpx.Response(status_code, content=content, headers=headers)
        return httpx.Response(
            status_code,
            json=payload if payload is not None else {"result": 0, "access_token": "tok"},
            headers=headers,
        )

    def factory(**kwargs: Any) -> httpx.Client:
        kwargs.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    with patch.object(httpx, "Client", factory):
        yield captured
