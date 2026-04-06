import pytest
from chat.tools.python_exec import PythonExecTool


@pytest.fixture
def pyexec(tmp_path):
    return PythonExecTool(sandbox_dir=str(tmp_path))


def test_definition(pyexec):
    assert pyexec.definition["name"] == "python_exec"


@pytest.mark.asyncio
async def test_basic_exec(pyexec):
    result = await pyexec.execute({"code": "print(2 + 2)"})
    assert result["stdout"].strip() == "4"


@pytest.mark.asyncio
async def test_error_output(pyexec):
    result = await pyexec.execute({"code": "raise ValueError('oops')"})
    assert "ValueError" in result.get("stderr", "")


@pytest.mark.asyncio
async def test_empty_code(pyexec):
    result = await pyexec.execute({"code": ""})
    assert "error" in result
