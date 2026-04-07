import pytest
from chat.tools.weather import WeatherTool


@pytest.fixture
def weather():
    return WeatherTool()


def test_definition(weather):
    assert weather.definition["name"] == "weather"


@pytest.mark.asyncio
async def test_empty_location(weather):
    result = await weather.execute({"location": ""})
    assert "error" in result
