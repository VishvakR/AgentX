from abc import ABC
import httpx
from typing import Any

# from SaraAgent.tools.registry import ToolRegistry
from SaraAgent.tools.base import Tool, tool_parameters
from SaraAgent.config.schema import Base

class WeatherConfig(Base):
    provider: str = "openmeteo"
    api_key: str = ""
    base_url: str = ""
    timeout: int = 30


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name, region, or coordinates to look up weather for.",
            },
            "units": {
                "type": "string",
                "enum": ["metric", "imperial"],
                "description": "Use metric or imperial units.",
            },
            "days": {
                "type": "integer",
                "minimum": 1,
                "maximum": 7,
                "description": "Forecast days to return.",
            },
            "current": {
                "type": "boolean",
                "description": "Include current weather in the response.",
            },
        },
        "required": ["location"],
    }
)
class WeatherTool(Tool):
    name = "weather"
    config_key = "weather"

    @classmethod
    def config_cls(cls):
        return WeatherConfig
    
    def __init__(self, config: WeatherConfig | None = None):
        self.config = config or WeatherConfig()


    @property
    def name(self) -> str:
        return "weather"
    
    @property
    def description(self) -> str:
        return "Get current weather information for a specified location."
    
    @property
    def read_only(self) -> bool:
        return True
    
    
    async def execute(
            self,
            location: str,
            units: str = "metric",
            days: int = 1,
            current: bool = True,
        ):

        async with httpx.AsyncClient(timeout=60) as client:
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            print(geo_data)
            results = geo_data.get("results") or []
            if not results:
                return f"Error: could not find location '{location}'"
            place = results[0]
            lat = place["latitude"]
            lon = place["longitude"]

            place_name = ", ".join(
                part
                for part in [
                    place.get("name"),
                    place.get("admin1"),
                    place.get("country"),
                ]
                if part
            )
            print(place_name)
            params: dict[str, Any] = {
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "forecast_days": 1,
                "daily": [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                ],
            }

            if "matrix" == "imperial":
                params["temperature_unit"] = "fahrenheit"
                params["windspeed_unit"] = "mph"
            else:
                params["temperature_unit"] = "celsius"
                params["windspeed_unit"] = "kmh"

            if True:
                params["current_weather"] = True

            weather_url = f"https://api.open-meteo.com/v1/forecast"
            weather_resp = await client.get(weather_url, params=params)
            weather_resp.raise_for_status()
            data = weather_resp.json()
            print(data)

            # 3) format result
            lines: list[str] = [f"Weather for {place_name}"]

            cur = data.get("current_weather")
            if cur:
                lines.append(
                    f"Current: {cur.get('temperature')}°, wind {cur.get('windspeed')} {params['windspeed_unit']}"
                )

            daily = data.get("daily") or {}
            dates = daily.get("time") or []
            tmax = daily.get("temperature_2m_max") or []
            tmin = daily.get("temperature_2m_min") or []
            rain = daily.get("precipitation_probability_max") or []

            if dates:
                lines.append("Forecast:")
                for i, day in enumerate(dates):
                    max_v = tmax[i] if i < len(tmax) else "?"
                    min_v = tmin[i] if i < len(tmin) else "?"
                    rain_v = rain[i] if i < len(rain) else "?"
                    lines.append(f"- {day}: {min_v}° to {max_v}°, rain chance {rain_v}%")

            return "\n".join(lines)