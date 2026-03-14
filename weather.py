import requests
import pandas as pd

lat, lon = 43.651070, -79.347015
base_url = "https://api.open-meteo.com/v1/forecast"

params = {
    "latitude": lat,
    "longitude": lon,
    "start_date": "2025-12-11",
    "end_date": "2026-03-13",
    "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "America/Toronto",
}

resp = requests.get(base_url, params=params)
data = resp.json()
print(data.keys())          # debug

if "daily" not in data:
    raise RuntimeError("No 'daily' in response, got: " + str(data))

daily = data["daily"]
df = pd.DataFrame({
    "date": daily["time"],
    "weathercode": daily["weathercode"],
    "tmax_c": daily["temperature_2m_max"],
    "tmin_c": daily["temperature_2m_min"],
    "precip_mm": daily["precipitation_sum"],
})

df.to_csv("toronto_weather_2026.csv", index=False)
print("Saved to CSV")
