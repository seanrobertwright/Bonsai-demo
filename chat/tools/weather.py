"""Weather tool — Open-Meteo (default) or OpenWeatherMap."""

import httpx

from chat.config import get_config


class WeatherTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "weather",
            "description": "Get current weather and 3-day forecast for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g., 'New York', 'London, UK')",
                    }
                },
                "required": ["location"],
            },
        }

    async def execute(self, params: dict) -> dict:
        location = params.get("location", "").strip()
        if not location:
            return {"error": "Empty location"}

        cfg = get_config()
        if cfg.get("openweather_key"):
            return await self._openweather(location, cfg["openweather_key"])
        return await self._open_meteo(location)

    async def _geocode(self, location: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1},
            )
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return {"lat": r["latitude"], "lon": r["longitude"], "name": r.get("name", location), "country": r.get("country", "")}

    async def _open_meteo(self, location: str) -> dict:
        try:
            geo = await self._geocode(location)
            if not geo:
                return {"error": f"Could not find location: {location}"}

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": geo["lat"],
                        "longitude": geo["lon"],
                        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                        "temperature_unit": "fahrenheit",
                        "forecast_days": 3,
                    },
                )
                data = resp.json()

            current = data.get("current", {})
            daily = data.get("daily", {})

            forecast = []
            times = daily.get("time", [])
            maxs = daily.get("temperature_2m_max", [])
            mins = daily.get("temperature_2m_min", [])
            codes = daily.get("weather_code", [])
            for i in range(len(times)):
                forecast.append({
                    "date": times[i],
                    "high": maxs[i] if i < len(maxs) else None,
                    "low": mins[i] if i < len(mins) else None,
                    "condition": self._weather_code_to_text(codes[i] if i < len(codes) else 0),
                })

            return {
                "location": f"{geo['name']}, {geo['country']}",
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "humidity": current.get("relative_humidity_2m"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "condition": self._weather_code_to_text(current.get("weather_code", 0)),
                },
                "forecast": forecast,
            }
        except Exception as e:
            return {"error": f"Weather lookup failed: {e}"}

    async def _openweather(self, location: str, api_key: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": location, "appid": api_key, "units": "imperial"},
                )
                data = resp.json()
            if data.get("cod") != 200:
                return {"error": data.get("message", "Unknown error")}
            return {
                "location": data.get("name", location),
                "current": {
                    "temperature": data["main"]["temp"],
                    "humidity": data["main"]["humidity"],
                    "wind_speed": data["wind"]["speed"],
                    "condition": data["weather"][0]["description"] if data.get("weather") else "unknown",
                },
            }
        except Exception as e:
            return {"error": f"OpenWeatherMap failed: {e}"}

    @staticmethod
    def _weather_code_to_text(code: int) -> str:
        codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        return codes.get(code, f"Code {code}")
