"""Mocked tests for every pCloud tool function."""

import pytest

from mcp_pcloud_crunchtools import tools
from mcp_pcloud_crunchtools.errors import (
    AuthenticationError,
    PathNotFoundError,
    PCloudApiError,
    PermissionDeniedError,
    RateLimitError,
    TwoFactorRequiredError,
)
from tests.helpers import mock_response, patch_client, text_response

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


class TestFolderTools:
    async def test_list_folder(self):
        payload = {"result": 0, "metadata": {"contents": [FILE_META, FOLDER_META]}}
        with patch_client(mock_response(payload)) as get:
            out = await tools.list_folder("/Documents", False)
        assert "report.pdf" in out
        assert "Documents/" in out
        assert get.call_args.kwargs["params"] == {"path": "/Documents"}

    async def test_list_folder_recursive_sets_flag(self):
        with patch_client(mock_response({"result": 0, "metadata": {"contents": []}})) as get:
            out = await tools.list_folder("/", True)
        assert get.call_args.kwargs["params"]["recursive"] == 1
        assert "(empty)" in out

    async def test_create_folder(self):
        with patch_client(mock_response({"result": 0, "created": True})):
            assert "Created" in await tools.create_folder("/New")

    async def test_create_folder_already_present(self):
        with patch_client(mock_response({"result": 0, "created": False})):
            assert "Already present" in await tools.create_folder("/New")

    async def test_delete_folder_non_recursive(self):
        with patch_client(mock_response({"result": 0})) as get:
            out = await tools.delete_folder("/Old", False)
        assert get.call_args.args[0] == "/deletefolder"
        assert "and its contents" not in out

    async def test_delete_folder_recursive(self):
        with patch_client(mock_response({"result": 0})) as get:
            out = await tools.delete_folder("/Old", True)
        assert get.call_args.args[0] == "/deletefolderrecursive"
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
    async def test_search(self):
        with patch_client(mock_response({"result": 0, "metadata": [FILE_META]})):
            assert "report.pdf" in await tools.search("report", "/")

    async def test_search_empty(self):
        with patch_client(mock_response({"result": 0, "metadata": []})):
            assert "(empty)" in await tools.search("nothing", "/")

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

        sent = {}

        async def fake_post(_self, url, **kwargs):
            sent["url"] = url
            sent["data"] = kwargs.get("data")
            return mock_response({"result": 0, "metadata": FILE_META})

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
        await tools.get_file_info("/Documents/report.pdf")

        assert sent["data"]["auth"] == "session-value"
        assert "session-value" not in sent["url"]

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
