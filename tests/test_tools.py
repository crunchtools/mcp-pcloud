"""Mocked tests for every pCloud tool function."""

import importlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_pcloud_crunchtools import config as config_module
from mcp_pcloud_crunchtools import tools
from mcp_pcloud_crunchtools.errors import (
    AuthenticationError,
    PathNotFoundError,
    PCloudApiError,
    PermissionDeniedError,
    RateLimitError,
    TwoFactorRequiredError,
)
from mcp_pcloud_crunchtools.server import mcp
from tests.helpers import (
    mock_response,
    params_of,
    patch_client,
    path_of,
    sent_request,
    text_response,
)

FILE_META = {
    "name": "report.pdf",
    "path": "/Documents/report.pdf",
    "size": 2048,
    "modified": "Mon, 05 Jan 2026 10:00:00 +0000",
    "isfolder": False,
}
FOLDER_META = {
    "name": "Documents",
    "path": "/Documents",
    "modified": "Mon, 05 Jan 2026 10:00:00 +0000",
    "isfolder": True,
}


def _listing(contents: list[dict[str, Any]]) -> httpx.Response:
    """One non-recursive listfolder response."""
    return mock_response({"result": 0, "metadata": {"contents": contents}})


class TestFolderTools:
    async def test_list_folder(self):
        payload = {"result": 0, "metadata": {"contents": [FILE_META, FOLDER_META]}}
        with patch_client(mock_response(payload)) as sent:
            out = await tools.list_folder("/Documents", False)
        assert "report.pdf" in out
        assert "Documents/" in out
        assert params_of(sent.call_args) == {"path": "/Documents"}

    async def test_list_folder_recursive_sets_flag(self):
        with patch_client(mock_response({"result": 0, "metadata": {"contents": []}})) as sent:
            out = await tools.list_folder("/", True)
        assert params_of(sent.call_args)["recursive"] == "1"
        assert "(empty)" in out

    async def test_create_folder(self):
        with patch_client(mock_response({"result": 0, "created": True})):
            assert "Created" in await tools.create_folder("/New")

    async def test_create_folder_already_present(self):
        with patch_client(mock_response({"result": 0, "created": False})):
            assert "Already present" in await tools.create_folder("/New")

    async def test_delete_folder_non_recursive(self):
        with patch_client(mock_response({"result": 0})) as sent:
            out = await tools.delete_folder("/Old", False)
        assert path_of(sent.call_args) == "/deletefolder"
        assert "and its contents" not in out

    async def test_delete_folder_recursive(self):
        with patch_client(mock_response({"result": 0})) as sent:
            out = await tools.delete_folder("/Old", True)
        assert path_of(sent.call_args) == "/deletefolderrecursive"
        assert "and its contents" in out

    async def test_rename_folder(self):
        with patch_client(mock_response({"result": 0})):
            assert "->" in await tools.rename_folder("/A", "/B")

    async def test_copy_folder(self):
        with patch_client(mock_response({"result": 0})):
            assert "Copied folder" in await tools.copy_folder("/A", "/B")


class TestFileTools:
    async def test_get_file_info(self):
        with patch_client(mock_response({"result": 0, "metadata": FILE_META})):
            out = await tools.get_file_info("/Documents/report.pdf")
        assert "report.pdf" in out
        assert "2.00 KB" in out

    async def test_delete_file(self):
        with patch_client(mock_response({"result": 0})):
            assert "Deleted file" in await tools.delete_file("/a.txt")

    async def test_rename_file(self):
        with patch_client(mock_response({"result": 0})):
            assert "Renamed file" in await tools.rename_file("/a.txt", "/b.txt")

    async def test_copy_file(self):
        with patch_client(mock_response({"result": 0})):
            assert "Copied file" in await tools.copy_file("/a.txt", "/b.txt")

    async def test_read_text_file(self):
        meta = {"result": 0, "hosts": ["c1.pcloud.com"], "path": "/dl/a.txt"}
        with patch_client(mock_response(meta), text_response("file body")):
            assert await tools.read_text_file("/a.txt") == "file body"

    async def test_read_text_file_requests_getfilelink(self):
        meta = {"result": 0, "hosts": ["c1.pcloud.com"], "path": "/dl/a.txt"}
        with patch_client(mock_response(meta), text_response("file body")) as sent:
            await tools.read_text_file("/a.txt")
        paths = [path_of(call) for call in sent.await_args_list]
        assert paths[0] == "/getfilelink"
        assert "gettextfile" not in "".join(paths)

    async def test_content_fetch_carries_no_authorization_header(self):
        from mcp_pcloud_crunchtools.client import get_client

        meta = {"result": 0, "hosts": ["c1.pcloud.com"], "path": "/dl/a.txt"}
        with patch_client(mock_response(meta), text_response("file body")) as sent:
            await tools.read_text_file("/a.txt")
        client = get_client()
        assert (await client._get_client()).headers["Authorization"] == "Bearer test-token-value"
        content_client = client._content_client
        assert content_client is not None
        assert "Authorization" not in content_client.headers
        assert str(content_client.base_url) == ""
        content_request = sent_request(sent.await_args_list[1])
        assert str(content_request.url) == "https://c1.pcloud.com/dl/a.txt"
        assert "Authorization" not in content_request.headers
        await client.close()

    async def test_read_text_file_without_host_errors(self):
        with (
            patch_client(mock_response({"result": 0, "hosts": []})),
            pytest.raises(PCloudApiError, match="no download host"),
        ):
            await tools.read_text_file("/a.txt")

    async def test_get_checksum(self):
        payload = {"result": 0, "sha256": "abc", "sha1": "def", "md5": "ghi"}
        with patch_client(mock_response(payload)):
            out = await tools.get_checksum("/a.txt")
        assert "SHA256: abc" in out
        assert "MD5: ghi" in out

    async def test_get_checksum_when_absent(self):
        with patch_client(mock_response({"result": 0})):
            assert "No checksums" in await tools.get_checksum("/a.txt")


class TestLinkTools:
    async def test_get_file_link(self):
        payload = {"result": 0, "hosts": ["c1.pcloud.com"], "path": "/dl/a.txt"}
        with patch_client(mock_response(payload)):
            out = await tools.get_file_link("/a.txt")
        assert "https://c1.pcloud.com/dl/a.txt" in out

    async def test_get_file_link_without_host_errors(self):
        with (
            patch_client(mock_response({"result": 0, "hosts": []})),
            pytest.raises(PCloudApiError, match="no download host"),
        ):
            await tools.get_file_link("/a.txt")

    async def test_create_public_link(self):
        with patch_client(mock_response({"result": 0, "link": "https://u.pcloud.link/x"})):
            assert "https://u.pcloud.link/x" in await tools.create_public_link("/a.txt")

    async def test_create_public_link_without_link_errors(self):
        with (
            patch_client(mock_response({"result": 0})),
            pytest.raises(PCloudApiError, match="no public link"),
        ):
            await tools.create_public_link("/a.txt")


class TestSearchAndAccount:
    async def test_search_filters_listfolder_tree(self):
        top = [
            {"name": "Other.txt", "isfolder": False, "size": 1},
            {"name": "Sub", "isfolder": True},
        ]
        sub = [{"name": "Gourmand-Draft.md", "isfolder": False, "size": 10}]
        with patch_client(_listing(top), _listing(sub)) as sent:
            out = await tools.search("gourmand", "/Projects")
        calls = [(path_of(call), params_of(call)) for call in sent.await_args_list]
        assert calls == [
            ("/listfolder", {"path": "/Projects"}),
            ("/listfolder", {"path": "/Projects/Sub"}),
        ]
        assert "Gourmand-Draft.md" in out
        assert "/Projects/Sub/Gourmand-Draft.md" in out
        assert "Other.txt" not in out

    async def test_search_at_root(self):
        top = [
            {"name": "Documents", "isfolder": True, "path": "/Documents"},
            {"name": "notes.txt", "isfolder": False},
        ]
        docs = [{"name": "Notes-2026.md", "isfolder": False, "path": "/Documents/Notes-2026.md"}]
        with patch_client(_listing(top), _listing(docs)) as sent:
            out = await tools.search("notes", "/")
        paths = [params_of(call)["path"] for call in sent.await_args_list]
        assert paths == ["/", "/Documents"]
        assert "recursive" not in params_of(sent.await_args_list[0])
        assert "/notes.txt" in out
        assert "/Documents/Notes-2026.md" in out

    async def test_search_lists_siblings_before_descendants(self):
        root = [{"name": "A", "isfolder": True}, {"name": "B", "isfolder": True}]
        a = [{"name": "A1", "isfolder": True}]
        b = [{"name": "B1", "isfolder": True}]
        with patch_client(
            _listing(root), _listing(a), _listing(b), _listing([]), _listing([])
        ) as sent:
            await tools.search("nothing", "/")
        paths = [params_of(call)["path"] for call in sent.await_args_list]
        assert paths == ["/", "/A", "/B", "/A/A1", "/B/B1"]

    async def test_search_fails_when_a_batched_listing_fails(self):
        root = [{"name": "A", "isfolder": True}, {"name": "Gone", "isfolder": True}]
        missing = mock_response({"result": 2005, "error": "Directory does not exist."})
        with (
            patch_client(_listing(root), _listing([]), missing),
            pytest.raises(PathNotFoundError),
        ):
            await tools.search("nothing", "/")

    async def test_search_empty(self):
        with patch_client(_listing([])):
            assert "(empty)" in await tools.search("nothing", "/")

    async def test_search_respects_depth_bound(self):
        # `tools.search` is the function, which shadows the submodule of the same name.
        search_module = importlib.import_module("mcp_pcloud_crunchtools.tools.search")

        levels = [
            _listing([{"name": f"d{i}", "isfolder": True}]) for i in range(search_module.MAX_DEPTH)
        ]
        with patch_client(*levels) as sent:
            out = await tools.search("hit-deep", "/")
        assert sent.await_count == search_module.MAX_DEPTH
        assert "(empty)" in out
        assert f"deeper than {search_module.MAX_DEPTH} levels" in out

    async def test_search_descends_to_depth_limit(self):
        # `tools.search` is the function, which shadows the submodule of the same name.
        search_module = importlib.import_module("mcp_pcloud_crunchtools.tools.search")

        levels = [
            _listing([{"name": f"d{i}", "isfolder": True}])
            for i in range(search_module.MAX_DEPTH - 1)
        ]
        levels.append(_listing([{"name": "hit-deep", "isfolder": False}]))
        with patch_client(*levels):
            out = await tools.search("hit-deep", "/")
        assert "hit-deep" in out
        assert "deeper than" not in out

    async def test_search_reports_depth_and_cap_together(self):
        # `tools.search` is the function, which shadows the submodule of the same name.
        search_module = importlib.import_module("mcp_pcloud_crunchtools.tools.search")

        files = [
            {"name": f"hit{i}.txt", "isfolder": False} for i in range(search_module.MAX_RESULTS + 1)
        ]
        levels = [
            _listing([{"name": f"d{i}", "isfolder": True}])
            for i in range(search_module.MAX_DEPTH - 1)
        ]
        levels.append(_listing([{"name": "deeper", "isfolder": True}, *files]))
        with patch_client(*levels):
            out = await tools.search("hit", "/")
        assert "truncated" in out
        assert "deeper than" in out

    async def test_search_truncates_at_cap(self):
        # `tools.search` is the function, which shadows the submodule of the same name.
        search_module = importlib.import_module("mcp_pcloud_crunchtools.tools.search")

        cap = search_module.MAX_RESULTS
        files = [{"name": f"hit{i}.txt", "isfolder": False} for i in range(cap + 5)]
        with patch_client(_listing(files)):
            out = await tools.search("hit", "/")
        assert out.count("[file]") == cap
        assert "truncated" in out

    async def test_search_stops_at_listing_cap(self):
        # `tools.search` is the function, which shadows the submodule of the same name.
        search_module = importlib.import_module("mcp_pcloud_crunchtools.tools.search")

        cap = search_module.MAX_LISTINGS
        wide = [{"name": f"f{i}", "isfolder": True} for i in range(cap + 10)]
        responses = [_listing(wide)] + [_listing([]) for _ in range(cap)]
        with patch_client(*responses) as sent:
            out = await tools.search("nothing", "/")
        assert sent.await_count == cap
        assert f"stopped after listing {cap} folders; narrow the path" in out
        assert "truncated" not in out

    async def test_get_user_info(self):
        payload = {
            "result": 0,
            "email": "user@example.com",
            "emailverified": True,
            "registered": "2020-01-01",
            "quota": 2 * 1024**3,
            "usedquota": 1024**3,
        }
        with patch_client(mock_response(payload)):
            out = await tools.get_user_info()
        assert "user@example.com" in out
        assert "1.00 GB (50.0%)" in out

    async def test_get_user_info_zero_quota(self):
        payload = {"result": 0, "email": "u@e.com", "quota": 0, "usedquota": 0}
        with patch_client(mock_response(payload)):
            assert "0.0%" in await tools.get_user_info()


class TestClientErrorHandling:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            (1000, AuthenticationError),
            (2000, AuthenticationError),
            (2297, TwoFactorRequiredError),
            (2005, PathNotFoundError),
            (2009, PathNotFoundError),
            (2003, PermissionDeniedError),
            (4000, RateLimitError),
            (5000, PCloudApiError),
        ],
    )
    async def test_result_codes_map_to_errors(self, code, expected):
        with (
            patch_client(mock_response({"result": code, "error": "boom"})),
            pytest.raises(expected),
        ):
            await tools.get_file_info("/a.txt")

    async def test_http_401_raises_auth_error(self):
        with (
            patch_client(mock_response({}, status_code=401)),
            pytest.raises(AuthenticationError),
        ):
            await tools.get_file_info("/a.txt")

    async def test_http_500_raises_api_error(self):
        with (
            patch_client(mock_response({}, status_code=500)),
            pytest.raises(PCloudApiError),
        ):
            await tools.get_file_info("/a.txt")

    async def test_token_scrubbed_from_error_message(self):
        payload = {"result": 5000, "error": "failed for test-token-value"}
        with (
            patch_client(mock_response(payload)),
            pytest.raises(PCloudApiError) as excinfo,
        ):
            await tools.get_file_info("/a.txt")
        assert "test-token-value" not in str(excinfo.value)
        assert "***" in str(excinfo.value)

    async def test_long_path_truncated_in_not_found(self):
        long_path = "/" + "x" * 200
        with (
            patch_client(mock_response({"result": 2009, "error": ""})),
            pytest.raises(PathNotFoundError) as excinfo,
        ):
            await tools.get_file_info(long_path)
        assert "..." in str(excinfo.value)
        assert len(str(excinfo.value)) < 100


class TestSessionTokenTransport:
    """A session token must travel in the POST body, never in a URL."""

    async def test_session_mode_posts_with_auth_in_body(self, monkeypatch):
        from mcp_pcloud_crunchtools import client as client_module
        from mcp_pcloud_crunchtools import config as config_module

        monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("PCLOUD_AUTH_TOKEN", "session-value")
        config_module._config = None
        client_module._client = None

        with patch_client(mock_response({"result": 0, "metadata": FILE_META})) as sent:
            await tools.get_file_info("/Documents/report.pdf")

        request = sent_request(sent.call_args)
        # Read off the wire rather than the kwargs, which is the only way to
        # show the token did not also end up in the query string.
        assert request.method == "POST"
        assert "auth=session-value" in request.content.decode()
        assert "session-value" not in str(request.url)

    async def test_oauth_mode_uses_get_with_bearer_header(self):
        with patch_client(mock_response({"result": 0, "metadata": FILE_META})):
            await tools.get_file_info("/a.txt")
        from mcp_pcloud_crunchtools.client import get_client

        client = await get_client()._get_client()
        assert client.headers["Authorization"] == "Bearer test-token-value"

    async def test_invalid_access_token_code_maps_to_auth_error(self):
        with (
            patch_client(mock_response({"result": 2094, "error": "bad"})),
            pytest.raises(AuthenticationError),
        ):
            await tools.get_file_info("/a.txt")


READ_ONLY = frozenset(
    {
        "pcloud_get_file_info",
        "pcloud_read_text_file",
        "pcloud_get_checksum",
        "pcloud_get_file_link",
        "pcloud_get_user_info",
        "pcloud_auth_status",
        "pcloud_list_folder",
        "pcloud_search",
    }
)
WRITES = frozenset(
    {
        "pcloud_create_folder",
        "pcloud_delete_folder",
        "pcloud_rename_folder",
        "pcloud_copy_folder",
        "pcloud_delete_file",
        "pcloud_rename_file",
        "pcloud_copy_file",
        # getfilepublink creates the public link it returns.
        "pcloud_create_public_link",
        # Replaces the pending CSRF state, which invalidates a login in flight.
        "pcloud_auth_start",
        # Only reports the last redirect's outcome, but it belongs to the flow
        # that stores a token, so it stays unannotated.
        "pcloud_auth_result",
    }
)

# pCloud sends reads and writes alike as GET (or, with a session token, all as
# POST), so the HTTP verb says nothing. What separates them is the API method
# in the path. These are the methods that change nothing in the account.
READ_METHODS = frozenset(
    {
        "stat",
        "checksumfile",
        # Mints a time-limited download URL; creates nothing in the account.
        "getfilelink",
        "userinfo",
        "listfolder",
    }
)

CONTENT_HOST = "c1.pcloud.com"

# Arguments for each read-only tool, and the pCloud payload that answers it.
READ_ONLY_CALLS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "pcloud_get_file_info": (
        {"path": "/Documents/report.pdf"},
        {"result": 0, "metadata": FILE_META},
    ),
    "pcloud_read_text_file": (
        {"path": "/notes.txt"},
        {"result": 0, "hosts": [CONTENT_HOST], "path": "/dl/notes.txt"},
    ),
    "pcloud_get_checksum": ({"path": "/a.bin"}, {"result": 0, "sha256": "abc"}),
    "pcloud_get_file_link": (
        {"path": "/a.bin"},
        {"result": 0, "hosts": [CONTENT_HOST], "path": "/dl/a.bin"},
    ),
    "pcloud_get_user_info": ({}, {"result": 0, "email": "a@b.c", "quota": 10}),
    "pcloud_auth_status": ({}, {"result": 0, "email": "a@b.c"}),
    "pcloud_list_folder": (
        {"path": "/Documents"},
        {"result": 0, "metadata": {"contents": [FILE_META]}},
    ),
    "pcloud_search": (
        {"query": "report", "path": "/Documents"},
        {"result": 0, "metadata": {"contents": [FILE_META]}},
    ),
}


async def _api_methods_called(name: str, tmp_path: Any, monkeypatch: Any) -> list[str]:
    """Call a registered tool against a mocked pCloud and return the API methods it hit.

    Runs in OAuth application mode with a stored token, the one mode in which
    every tool, pcloud_auth_status included, reaches pCloud. Also asserts the
    token store, the only thing this server keeps on disk, is left untouched.
    """
    arguments, payload = READ_ONLY_CALLS.get(name, ({"path": "/a.bin"}, {"result": 0, "link": "x"}))
    store = tmp_path / "tokens.json"
    store.write_text(json.dumps({"access_token": "stored-token", "api_host": "api.pcloud.com"}))
    monkeypatch.delenv("PCLOUD_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("PCLOUD_CLIENT_ID", "cid")
    monkeypatch.setenv("PCLOUD_CLIENT_SECRET", "csec")
    monkeypatch.setenv("PCLOUD_TOKEN_STORE_PATH", str(store))
    config_module._config = None
    before = (store.read_bytes(), store.stat().st_mtime_ns, sorted(tmp_path.iterdir()))

    async def fake_send(request: httpx.Request, **_kwargs: Any) -> httpx.Response:
        if request.url.host == CONTENT_HOST:
            return text_response("file body")
        return mock_response(payload)

    send = AsyncMock(side_effect=fake_send)
    sync_send = MagicMock()
    with (
        patch.object(httpx.AsyncClient, "send", send),
        patch.object(httpx.Client, "send", sync_send),
    ):
        await mcp.call_tool(name, arguments)

    # The sync client exists only for the token exchange, which stores a
    # credential: a read-only tool has no business reaching it.
    sync_send.assert_not_called()
    assert (store.read_bytes(), store.stat().st_mtime_ns, sorted(tmp_path.iterdir())) == before
    requests = [sent_request(call) for call in send.await_args_list]
    # The HTTP verb is the read/write signal now that one send path carries
    # both: the API is GET under OAuth, and a write would be a POST.
    assert all(request.method == "GET" for request in requests)
    # A content host is the download pCloud pointed at; the rest are API methods.
    api = [request for request in requests if request.url.host != CONTENT_HOST]
    assert all(request.url.host == CONTENT_HOST for request in requests if request not in api)
    return [request.url.path.removeprefix("/") for request in api]


class TestReadOnlyAnnotation:
    """Every registered tool is classified, and the reads really only read."""

    async def test_every_tool_is_classified(self):
        registered = await mcp.list_tools()
        assert READ_ONLY.isdisjoint(WRITES)
        assert {tool.name for tool in registered} == READ_ONLY | WRITES
        annotated = {
            tool.name
            for tool in registered
            if tool.annotations is not None
            and tool.annotations.model_dump(by_alias=True).get("readOnlyHint") is True
        }
        assert annotated == READ_ONLY

    @pytest.mark.parametrize("name", ["pcloud_list_folder", "pcloud_search"])
    async def test_path_is_required(self, name):
        tool = next(t for t in await mcp.list_tools() if t.name == name)
        assert "path" in tool.parameters["required"]

    @pytest.mark.parametrize("name", sorted(READ_ONLY))
    async def test_read_only_tool_calls_only_read_methods(self, name, tmp_path, monkeypatch):
        methods = await _api_methods_called(name, tmp_path, monkeypatch)
        assert methods, f"{name} never reached pCloud"
        assert set(methods) <= READ_METHODS

    async def test_a_write_is_caught_by_the_method_check(self, tmp_path, monkeypatch):
        """The check above can fail: a tool that creates a link is outside READ_METHODS."""
        methods = await _api_methods_called("pcloud_create_public_link", tmp_path, monkeypatch)
        assert methods == ["getfilepublink"]
        assert not set(methods) <= READ_METHODS
