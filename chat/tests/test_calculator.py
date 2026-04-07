import pytest
from chat.tools.calculator import CalculatorTool


@pytest.fixture
def calc():
    return CalculatorTool()


def test_definition(calc):
    d = calc.definition
    assert d["name"] == "calculator"
    assert "parameters" in d


@pytest.mark.asyncio
async def test_basic_arithmetic(calc):
    result = await calc.execute({"expression": "2 + 3 * 4"})
    assert result["result"] == "14"


@pytest.mark.asyncio
async def test_symbolic_math(calc):
    result = await calc.execute({"expression": "sqrt(144)"})
    assert result["result"] == "12"


@pytest.mark.asyncio
async def test_invalid_expression(calc):
    result = await calc.execute({"expression": "import os"})
    assert "error" in result
