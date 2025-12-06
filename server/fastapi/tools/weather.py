import httpx
from langchain_core.tools import tool

# HTTP client for external API calls
http_client = httpx.Client(timeout=10.0)


def geocode_location(location: str) -> tuple[float, float, str] | None:
    """Convert a location name to coordinates using Open-Meteo Geocoding API.
    
    Returns (latitude, longitude, display_name) or None if not found.
    """
    search_name = location
    if "," in location:
        city_part = location.split(",")[0].strip()
        search_name = city_part
    
    response = http_client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": search_name, "count": 1, "language": "en", "format": "json"},
    )
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    if not data.get("results"):
        if search_name != location:
            response = http_client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            if response.status_code == 200:
                data = response.json()
        
        if not data.get("results"):
            return None
    
    result = data["results"][0]
    display_name = result.get("name", location)
    if result.get("admin1"):
        display_name += f", {result['admin1']}"
    if result.get("country"):
        display_name += f", {result['country']}"
    
    return (result["latitude"], result["longitude"], display_name)


def get_weather_code_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return weather_codes.get(code, "Unknown conditions")


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location.

    Args:
        location: The city and state, e.g. "San Francisco, CA"
    """
    geo_result = geocode_location(location)
    if not geo_result:
        return f"Could not find location: {location}"
    
    lat, lon, display_name = geo_result
    
    response = http_client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        },
    )
    
    if response.status_code != 200:
        return f"Error fetching weather data for {location}"
    
    data = response.json()
    current = data.get("current", {})
    
    temp = current.get("temperature_2m", "N/A")
    humidity = current.get("relative_humidity_2m", "N/A")
    weather_code = current.get("weather_code", 0)
    wind_speed = current.get("wind_speed_10m", "N/A")
    
    condition = get_weather_code_description(weather_code)
    
    return f"{display_name}: {condition}, {temp}°F, Humidity: {humidity}%, Wind: {wind_speed} mph"

