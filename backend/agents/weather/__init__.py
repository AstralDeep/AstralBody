"""
Weather Agent package for AstralBody system.

Provides weather data and forecast tools using Open-Meteo API.
"""

from agents.weather.weather_agent import WeatherAgent
from agents.weather.mcp_server import MCPServer
from agents.weather.mcp_tools import (
    geocode_location,
    get_current_weather,
    get_hourly_forecast,
    get_daily_forecast,
    get_weekly_forecast,
    TOOL_REGISTRY
)

__all__ = [
    'WeatherAgent',
    'MCPServer',
    'geocode_location',
    'get_current_weather',
    'get_hourly_forecast',
    'get_daily_forecast',
    'get_weekly_forecast',
    'TOOL_REGISTRY'
]

__version__ = '1.0.0'
