"""Server registration tests."""

from mcp_pcloud_crunchtools.server import mcp

EXPECTED_TOOL_COUNT = 15

EXPECTED_TOOLS = {
    "pcloud_list_folder",
    "pcloud_create_folder",
    "pcloud_delete_folder",
    "pcloud_rename_folder",
    "pcloud_copy_folder",
    "pcloud_get_file_info",
    "pcloud_delete_file",
    "pcloud_rename_file",
    "pcloud_copy_file",
    "pcloud_read_text_file",
    "pcloud_get_checksum",
    "pcloud_get_file_link",
    "pcloud_create_public_link",
    "pcloud_search",
    "pcloud_get_user_info",
}


async def test_tool_count():
    tools = await mcp.get_tools()
    assert len(tools) == EXPECTED_TOOL_COUNT


async def test_tool_names():
    tools = await mcp.get_tools()
    assert set(tools) == EXPECTED_TOOLS


async def test_every_tool_has_a_description():
    tools = await mcp.get_tools()
    assert all(tool.description for tool in tools.values())


async def test_tools_module_exports_match_registrations():
    from mcp_pcloud_crunchtools import tools as tools_module

    assert len(tools_module.__all__) == EXPECTED_TOOL_COUNT
