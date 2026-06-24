---
name: "weather_techniques"
type: technique
agent: "weather-1"
authored: true
relevance: [weather, forecast, temperature, rain, location, climate]
updated_at: "2026-06-24"
---

# Weather — effective use

## Effective Patterns
- Resolve a place name to coordinates with `geocode_location` first when the
  user gives a city/landmark rather than coordinates.
- Pick the forecast granularity that matches the question: `get_hourly_forecast`
  for "today/tonight", `get_daily_forecast`/`get_weekly_forecast` for multi-day.
- Use `compare_locations` for "which is warmer/wetter" style questions instead
  of separate calls the user must compare by eye.

## Anti-Patterns
- Do not guess coordinates for an ambiguous place — geocode, and if ambiguous,
  ask which one.

## Recommended Tool Sequences
- "weather in <city> this week" → `geocode_location` → `get_weekly_forecast`.
- "is it warmer in A or B" → `compare_locations`.
