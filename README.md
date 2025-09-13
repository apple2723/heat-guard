# HeatGuard (Python-only)

HeatGuard is a Python-based web app that helps outdoor workers and students stay safe during extreme heat by turning real-time weather data into personalized safety plans — including heat risk scores, safe outdoor time windows, and role-based hydration + rest schedules.

**Hyperlocal heat-risk coach** for outdoor workers & students — built **entirely in Python** using **Streamlit**.

## Features
- Next-24h **heat index** & **risk** (Low/Moderate/High/Extreme)
- **Safer outdoor windows** by hour
- **Role-based guidance:** work/rest cycle & hydration plan
- **Hydration schedule** timeline and simple session timer
- **Printable daily bulletin** (download .txt)
- City geocoding or lat/lon input

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
export OPENWEATHER_KEY=YOUR_KEY   # Windows: set OPENWEATHER_KEY=YOUR_KEY
You can get a free key at [https://home.openweathermap.org/api_keys](https://home.openweathermap.org/api_keys)
streamlit run app.py
```

## Notes
- Uses OpenWeather One Call API (imperial units) for hourly forecast.
- If UVI >= 8, adds a small +3°F "sun exposure" bump to guidance-only HI.
- All logic & UI are 100% Python
