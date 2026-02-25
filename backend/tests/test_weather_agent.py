#!/usr/bin/env python3
"""
Integration tests for WeatherAgent.

Tests the weather agent's tools and integration with the Open-Meteo API.
Note: These tests make real API calls to Open-Meteo (free tier, rate limited).
"""
import pytest
import sys
import os
import json
from unittest.mock import Mock, patch

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.weather.mcp_tools import (
    geocode_location,
    get_current_weather,
    get_hourly_forecast,
    get_daily_forecast,
    get_weekly_forecast,
    _make_api_request
)


class TestWeatherAgent:
    """Test suite for WeatherAgent tools."""
    
    @pytest.fixture
    def mock_geocode_response(self):
        """Mock response for geocoding API."""
        return {
            "results": [
                {
                    "name": "New York",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "country": "United States",
                    "admin1": "New York",
                    "timezone": "America/New_York",
                    "population": 8336817
                }
            ]
        }
    
    @pytest.fixture
    def mock_weather_response(self):
        """Mock response for weather API."""
        return {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "current": {
                "time": "2024-01-01T12:00",
                "temperature_2m": 72.5,
                "apparent_temperature": 75.0,
                "relative_humidity_2m": 65,
                "precipitation": 0.1,
                "weather_code": 1,
                "wind_speed_10m": 8.5,
                "wind_direction_10m": 45,
                "pressure_msl": 1013.2
            }
        }
    
    @pytest.fixture
    def mock_forecast_response(self):
        """Mock response for forecast API."""
        return {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "hourly": {
                "time": ["2024-01-01T12:00", "2024-01-01T13:00", "2024-01-01T14:00"],
                "temperature_2m": [72.5, 74.0, 73.2],
                "precipitation_probability": [10, 15, 20]
            },
            "daily": {
                "time": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "temperature_2m_max": [75.0, 76.0, 74.0],
                "temperature_2m_min": [65.0, 66.0, 64.0],
                "precipitation_sum": [0.1, 0.2, 0.0]
            }
        }
    
    def test_geocode_location_success(self, mock_geocode_response):
        """Test successful geocoding of a location."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.return_value = mock_geocode_response
            
            result = geocode_location(city="New York", state="NY", country="US")
            
            assert "_ui_components" in result
            assert "_data" in result
            assert result["_data"]["name"] == "New York"
            assert result["_data"]["latitude"] == 40.7128
            assert result["_data"]["longitude"] == -74.0060
    
    def test_geocode_location_no_results(self):
        """Test geocoding with no results."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.return_value = {"results": []}
            
            result = geocode_location(city="Nonexistent City", state="XX")
            
            # Should return error UI components
            assert "_ui_components" in result
            # Check that it contains an alert
            components = result["_ui_components"]
            assert any("alert" in str(comp).lower() for comp in components)
    
    def test_get_current_weather_with_coordinates(self, mock_weather_response):
        """Test getting current weather with direct coordinates."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.return_value = mock_weather_response
            
            result = get_current_weather(latitude=40.7128, longitude=-74.0060)
            
            assert "_ui_components" in result
            assert "_data" in result
            assert result["_data"]["current"]["temperature_2m"] == 72.5
            
            # Should contain metric cards
            components = result["_ui_components"]
            assert len(components) > 0
    
    def test_get_current_weather_with_city(self, mock_geocode_response, mock_weather_response):
        """Test getting current weather with city name (requires geocoding)."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            # First call for geocoding, second for weather
            mock_api.side_effect = [mock_geocode_response, mock_weather_response]
            
            result = get_current_weather(city="New York", state="NY")
            
            assert "_ui_components" in result
            assert "_data" in result
            assert result["_data"]["location"] == "New York, NY"
    
    def test_get_hourly_forecast(self, mock_geocode_response, mock_forecast_response):
        """Test getting hourly forecast."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.side_effect = [mock_geocode_response, mock_forecast_response]
            
            result = get_hourly_forecast(city="New York", state="NY", hours=3)
            
            assert "_ui_components" in result
            assert "_data" in result
            assert len(result["_data"]["hourly_data"]["times"]) == 3
            assert len(result["_data"]["hourly_data"]["temperatures"]) == 3
            
            # Should contain a PlotlyChart
            components = result["_ui_components"]
            assert any("plotly" in str(comp).lower() for comp in components)
    
    def test_get_daily_forecast(self, mock_geocode_response, mock_forecast_response):
        """Test getting daily forecast."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.side_effect = [mock_geocode_response, mock_forecast_response]
            
            result = get_daily_forecast(city="New York", state="NY", days=3)
            
            assert "_ui_components" in result
            assert "_data" in result
            assert len(result["_data"]["daily_data"]["dates"]) == 3
            assert len(result["_data"]["daily_data"]["max_temperatures"]) == 3
            
            # Should contain a bar chart
            components = result["_ui_components"]
            assert any("plotly" in str(comp).lower() for comp in components)
    
    def test_get_weekly_forecast(self, mock_geocode_response, mock_forecast_response):
        """Test getting weekly forecast summary."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            # Mock for geocoding and daily forecast (weekly calls daily internally)
            mock_api.side_effect = [mock_geocode_response, mock_forecast_response]
            
            result = get_weekly_forecast(city="New York", state="NY")
            
            assert "_ui_components" in result
            assert "_data" in result
            assert "weekly_stats" in result["_data"]
            assert "average_high" in result["_data"]["weekly_stats"]
            
            # Should contain metric cards for weekly stats
            components = result["_ui_components"]
            assert len(components) > 0
    
    def test_api_error_handling(self):
        """Test error handling for API failures."""
        with patch('agents.weather.mcp_tools._make_api_request') as mock_api:
            mock_api.side_effect = Exception("API timeout")
            
            result = get_current_weather(latitude=40.7128, longitude=-74.0060)
            
            # Should return error UI components
            assert "_ui_components" in result
            components = result["_ui_components"]
            # Should contain an error alert
            assert any("error" in str(comp).lower() for comp in components)
    
    @pytest.mark.integration
    def test_integration_geocode_real_api(self):
        """Integration test with real Open-Meteo geocoding API."""
        # Skip if we want to avoid hitting real API in tests
        if os.getenv("SKIP_REAL_API_TESTS", "false").lower() == "true":
            pytest.skip("Skipping real API tests")
        
        try:
            result = geocode_location(city="London", country="GB")
            
            # Should have data
            assert "_data" in result
            data = result["_data"]
            
            # Should have coordinates
            assert "latitude" in data
            assert "longitude" in data
            
            # London should be around 51.5 latitude
            assert 51.0 < data["latitude"] < 52.0
            
        except Exception as e:
            # If rate limited or network error, skip but log
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                pytest.skip(f"API rate limited or timeout: {e}")
            else:
                raise
    
    @pytest.mark.integration
    def test_integration_current_weather_real_api(self):
        """Integration test with real Open-Meteo weather API."""
        if os.getenv("SKIP_REAL_API_TESTS", "false").lower() == "true":
            pytest.skip("Skipping real API tests")
        
        try:
            # Use a well-known location
            result = get_current_weather(latitude=40.7128, longitude=-74.0060)
            
            assert "_ui_components" in result
            assert "_data" in result
            
            data = result["_data"]
            assert "current" in data
            
            # Current weather should have temperature
            current = data["current"]
            assert "temperature_2m" in current
            
        except Exception as e:
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                pytest.skip(f"API rate limited or timeout: {e}")
            else:
                raise


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])