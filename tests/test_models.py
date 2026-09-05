"""Input validation tests."""

import pytest
from pydantic import ValidationError

from mcp_pcloud_crunchtools.models import (
    ListFolderInput,
    MoveInput,
    PathInput,
    SearchInput,
)


def test_valid_minimal_path():
    assert PathInput(path="/a.txt").path == "/a.txt"


def test_trailing_slash_collapsed():
    assert PathInput(path="/Documents/").path == "/Documents"


def test_root_path_preserved():
    assert ListFolderInput(path="/").path == "/"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "relative/path",
        "/etc/../../secret",
        "/a/../../../etc/passwd",
        "/nul\x00byte",
    ],
)
def test_rejected_paths(bad):
    with pytest.raises(ValidationError):
        PathInput(path=bad)


def test_path_length_limit():
    with pytest.raises(ValidationError):
        PathInput(path="/" + "a" * 5000)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        PathInput(path="/a.txt", unexpected="value")


def test_move_validates_both_paths():
    with pytest.raises(ValidationError):
        MoveInput(path="/ok.txt", to_path="../escape")


def test_empty_query_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="  ")


def test_long_query_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="x" * 500)


def test_search_defaults_to_root():
    assert SearchInput(query="report").path == "/"
