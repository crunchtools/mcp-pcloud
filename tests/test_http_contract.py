"""The outbound HTTP contract (constitution v1.36.0, MCP Server profile Layer 3).

A real `httpx.AsyncClient` over a `MockTransport`: the agent string is a header
the client adds and the ceiling is enforced while the client reads, so the
`patch_client` helper -- which scripts `send` -- cannot see either.

There are three read paths here, not one: the API, a content download, and the
OAuth token exchange. Each is tested, because the previous version checked
`len(response.content)` in all three and the fix had to reach all three.
"""

import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from importlib.metadata import version
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from mcp_pcloud_crunchtools import auth as auth_mod
from mcp_pcloud_crunchtools import client as client_mod
from mcp_pcloud_crunchtools.errors import AuthenticationError, PCloudApiError

Handler = Callable[[httpx.Request], httpx.Response]
CONTENT_URL = "https://c1.pcloud.com/dl/notes.txt?code=signed-value"


async def _chunks(chunk: bytes, times: int) -> AsyncIterator[bytes]:
    """A chunked body, which carries no content-length -- what a header check misses."""
    for _ in range(times):
        yield chunk


def _sync_chunks(chunk: bytes, times: int) -> Iterator[bytes]:
    """The same, for the token exchange, which is synchronous."""
    for _ in range(times):
        yield chunk


@contextmanager
def _serving(handler: Handler) -> Iterator[client_mod.PCloudClient]:
    """Hand back a client whose own `_get_client` rides a mock transport."""
    env = {"PCLOUD_ACCESS_TOKEN": "test-token-value"}  # gatehouse: allow-secret
    real = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(httpx, "AsyncClient", factory),
    ):
        yield client_mod.PCloudClient()


@contextmanager
def _exchanging(handler: Handler) -> Iterator[None]:
    """Put a mock transport under the sync client the token exchange creates."""
    real = httpx.Client

    def factory(**kwargs: Any) -> httpx.Client:
        kwargs.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    with patch.object(httpx, "Client", factory):
        yield


def _exchange() -> None:
    """One token exchange, with everything but the HTTP call already decided."""
    auth_mod._exchange_code(
        client_id="cid",
        client_secret=SecretStr("csec"),
        code="the-code",
        api_host="api.pcloud.com",
    )


class TestUserAgent:
    """Every one of the three paths says what it is, with the same version."""

    @pytest.mark.asyncio
    async def test_the_api_request_names_the_product_and_version(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["User-Agent"])
            return httpx.Response(200, json={"result": 0})

        with _serving(handler) as client:
            await client.call("listfolder", {"path": "/"})
            await client.close()

        expected = (
            f"mcp-pcloud-crunchtools/{version('mcp-pcloud-crunchtools')} "
            "(+https://github.com/crunchtools/mcp-pcloud)"
        )
        assert seen == [expected]

    @pytest.mark.asyncio
    async def test_a_content_download_names_it_too(self) -> None:
        """The content client is a second client, so it needs its own header."""
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["User-Agent"])
            return httpx.Response(200, text="file body")

        with _serving(handler) as client:
            await client.fetch_text(CONTENT_URL)
            await client.close()

        assert seen == [client_mod.USER_AGENT]

    def test_the_token_exchange_names_it_too(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["User-Agent"])
            return httpx.Response(200, json={"result": 0, "access_token": "tok"})

        with _exchanging(handler):
            _exchange()

        assert seen == [client_mod.USER_AGENT]

    def test_the_version_comes_from_package_metadata(self) -> None:
        """Not a literal: a literal drifts from pyproject.toml at the next release."""
        assert version("mcp-pcloud-crunchtools") in client_mod.USER_AGENT


class TestResponseCeiling:
    """`len(response.content)` measured a body that had already arrived."""

    @pytest.mark.asyncio
    async def test_a_chunked_api_body_over_the_cap_is_refused(self) -> None:
        over = client_mod.MAX_RESPONSE_SIZE // 1024 + 1

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_chunks(b"x" * 1024, over))

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert "byte limit" in str(caught.value)

    @pytest.mark.asyncio
    async def test_one_oversized_chunk_is_refused_before_it_is_copied(self) -> None:
        """`aiter_bytes()` promises nothing about chunk size: one can be the body."""
        whole = b"y" * (client_mod.MAX_RESPONSE_SIZE + 1)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_chunks(whole, 1))

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert "byte limit" in str(caught.value)

    @pytest.mark.asyncio
    async def test_a_content_download_has_the_ceiling_too(self) -> None:
        """The second read path. A file download is the likeliest body to be huge."""
        over = client_mod.MAX_RESPONSE_SIZE // 1024 + 1

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_chunks(b"z" * 1024, over))

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.fetch_text(CONTENT_URL)

        assert "byte limit" in str(caught.value)

    def test_the_token_exchange_has_the_ceiling_too(self) -> None:
        """A token response is a few JSON fields; a page answering there is not."""
        over = auth_mod.MAX_RESPONSE_SIZE // 1024 + 1

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_sync_chunks(b"w" * 1024, over))

        with _exchanging(handler), pytest.raises(AuthenticationError) as caught:
            _exchange()

        assert "byte limit" in str(caught.value)


class TestDeclaredLength:
    """A content-length over the cap is an early reject, not the only check."""

    @pytest.mark.asyncio
    async def test_a_declared_length_over_the_cap_is_rejected(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            response = httpx.Response(200, json={"result": 0})
            response.headers["content-length"] = str(client_mod.MAX_RESPONSE_SIZE + 1)
            return response

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert "declared" in str(caught.value)

    @pytest.mark.asyncio
    async def test_a_malformed_declared_length_does_not_crash(self) -> None:
        """Three repos in this fleet called `int()` on it unguarded."""

        def handler(_request: httpx.Request) -> httpx.Response:
            response = httpx.Response(200, json={"result": 0})
            response.headers["content-length"] = "not-a-number"
            return response

        with _serving(handler) as client:
            payload = await client.call("listfolder", {"path": "/"})

        assert payload == {"result": 0}


class TestErrorNamesTheSite:
    """RT #1596: the error named neither the site nor the body for an afternoon."""

    @pytest.mark.asyncio
    async def test_a_challenge_page_is_quoted_with_the_request(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503,
                headers={"content-type": "text/html"},
                text="<title>Just a moment...</title>",
            )

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        message = str(caught.value)
        assert "GET https://api.pcloud.com/listfolder?path=%2F" in message
        assert "HTTP 503" in message
        assert "text/html" in message
        assert "Just a moment" in message

    @pytest.mark.asyncio
    async def test_a_non_json_body_says_so_rather_than_blaming_the_parser(self) -> None:
        """`Malformed JSON from listfolder` gave a reader nothing to act on."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text="<html>login</html>"
            )

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        message = str(caught.value)
        assert "is not JSON" in message
        assert "https://api.pcloud.com/listfolder" in message
        assert "<html>login</html>" in message

    @pytest.mark.asyncio
    async def test_an_empty_body_says_so(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"")

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert "<empty body>" in str(caught.value)


class TestTheNamedUrlCarriesNoSignature:
    """A content URL is signed, so naming it has to not publish the signature."""

    @pytest.mark.asyncio
    async def test_the_signing_code_is_redacted(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, headers={"content-type": "text/html"}, text="gone")

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.fetch_text(CONTENT_URL)

        message = str(caught.value)
        assert "signed-value" not in message
        # `***` percent-encodes on its way back into the URL, which is the
        # fleet's redaction marker rather than a prettier word for the sake of
        # one assertion.
        assert "code=%2A%2A%2A" in message
        # The rest of the URL still has to be there, or the error is no better
        # than the status code it replaced.
        assert "c1.pcloud.com/dl/notes.txt" in message

    @pytest.mark.asyncio
    async def test_userinfo_is_dropped(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable")

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.fetch_text("https://user:secret@c1.pcloud.com/dl/a.txt")

        assert "secret" not in str(caught.value)


class TestTransportFailuresNameTheRequest:
    """A timeout with no endpoint in it is the hardest failure to place."""

    @pytest.mark.asyncio
    async def test_a_timeout_names_the_request(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout")

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert str(caught.value) == (
            "pCloud API error 0: GET https://api.pcloud.com/listfolder?path=%2F timed out: timeout"
        )

    @pytest.mark.asyncio
    async def test_a_connection_failure_names_the_request(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert str(caught.value) == (
            "pCloud API error 0: GET https://api.pcloud.com/listfolder?path=%2F failed: no route"
        )

    @pytest.mark.asyncio
    async def test_a_failure_mid_stream_is_still_a_pcloud_error(self) -> None:
        """The streaming read is a new failure point: the old code read eagerly."""

        async def failing() -> AsyncIterator[bytes]:
            yield b'{"result"'
            raise httpx.ReadTimeout("died")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=failing())

        with _serving(handler) as client, pytest.raises(PCloudApiError) as caught:
            await client.call("listfolder", {"path": "/"})

        assert "timed out" in str(caught.value)


class TestTheTokenExchangeQuotesNoBody:
    """The one endpoint whose body is a credential."""

    def test_an_html_page_on_the_token_url_is_not_quoted(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html>sso interstitial access_token=leaked</html>",
            )

        with _exchanging(handler), pytest.raises(AuthenticationError) as caught:
            _exchange()

        message = str(caught.value)
        assert "leaked" not in message
        assert "interstitial" not in message
        # The whole message, not a substring: CodeQL is right that a
        # `"api.pcloud.com" in message` test also passes for a host that
        # merely contains it, and this says what the reader actually gets --
        # where it went and what went wrong, and nothing from the body.
        assert message == (
            "pCloud authentication failed: Token exchange with api.pcloud.com "
            "failed: Expecting value: line 1 column 1 (char 0). Run "
            "`mcp-pcloud-crunchtools login` to authorize again, or set "
            "PCLOUD_ACCESS_TOKEN (or PCLOUD_ACCESS_TOKEN_FILE) to a valid "
            "OAuth access token."
        )
