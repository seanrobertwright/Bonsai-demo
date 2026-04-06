import pytest
from chat.tools.file_io import FileIOTool


@pytest.fixture
def file_tool(tmp_path):
    return FileIOTool(sandbox_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_definition(file_tool):
    assert file_tool.definition["name"] == "file_io"


@pytest.mark.asyncio
async def test_write_and_read(file_tool, tmp_path):
    result = await file_tool.execute({"action": "write", "path": "test.txt", "content": "hello world"})
    assert "written" in result.get("result", "").lower() or "Written" in result.get("result", "")

    result = await file_tool.execute({"action": "read", "path": "test.txt"})
    assert result["content"] == "hello world"


@pytest.mark.asyncio
async def test_list_directory(file_tool, tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = await file_tool.execute({"action": "list", "path": "."})
    assert "files" in result
    assert len(result["files"]) == 2


@pytest.mark.asyncio
async def test_path_traversal_blocked(file_tool):
    result = await file_tool.execute({"action": "read", "path": "../../etc/passwd"})
    assert "error" in result


@pytest.mark.asyncio
async def test_read_nonexistent(file_tool):
    result = await file_tool.execute({"action": "read", "path": "nope.txt"})
    assert "error" in result
