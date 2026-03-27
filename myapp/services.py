import requests
import urllib.parse
import json
from django.conf import settings
from groq import Groq

# ====================== API Keys ======================
OPENWEATHER_API_KEY = getattr(settings, 'OPENWEATHER_API_KEY', "219ff162a58589430fc465f29dd1d386")
RAPIDAPI_KEY = getattr(settings, 'RAPIDAPI_KEY', "e7453d4e41mshd1f8ba74c40c14fp1f6f91jsn61b5d9d6ade5")
RAPIDAPI_HOST = "travel-advisor.p.rapidapi.com"

# Groq Configuration
GROQ_API_KEY = getattr(settings, 'GROQ_API_KEY', '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')
GROQ_MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=GROQ_API_KEY)


def get_destination_weather(city_name):
    """Fetches real-time weather data from OpenWeatherMap."""
    if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY.startswith("219ff162"):
        return {"condition": "Clear", "temp": 28, "description": "clear sky"}

    url = f"http://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city_name)}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=8)
        if response.status_code == 200:
            data = response.json()
            return {
                "condition": data['weather'][0]['main'],
                "temp": round(data['main']['temp']),
                "description": data['weather'][0]['description']
            }
    except Exception as e:
        print(f"Weather API Error for {city_name}: {e}")

    return {"condition": "Clear", "temp": 25, "description": "clear sky"}


def get_local_events(location_name):
    """Improved: Real Travel Advisor API with robust parsing + fallback"""
    if not RAPIDAPI_KEY:
        return get_mock_events(location_name)

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    def extract_location_id(data):
        if not data:
            return None

        if isinstance(data, list):
            for item in data[:3]:
                if isinstance(item, dict):
                    loc_id = item.get("location_id") or item.get("geoId") or item.get("result_object", {}).get("location_id")
                    if loc_id:
                        return loc_id

        if isinstance(data, dict):
            data_list = data.get("data") or data.get("results")
            if isinstance(data_list, list):
                for item in data_list[:3]:
                    if isinstance(item, dict):
                        loc_id = (item.get("location_id") or item.get("geoId") or 
                                  item.get("result_object", {}).get("location_id") or item.get("locationId"))
                        if loc_id:
                            return loc_id

            for key in ["location_id", "geoId", "locationId"]:
                if key in data:
                    return data[key]
        return None

    # Try search
    search_url = f"https://{RAPIDAPI_HOST}/locations/search"
    params = {"query": location_name, "limit": "5", "offset": "0", "units": "km", "lang": "en_US"}

    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            location_id = extract_location_id(data)
            if location_id:
                return fetch_attractions(location_id, headers, location_name)

        # Auto-complete fallback
        auto_url = f"https://{RAPIDAPI_HOST}/locations/v2/auto-complete"
        auto_params = {"query": location_name, "lang": "en_US"}
        auto_resp = requests.get(auto_url, headers=headers, params=auto_params, timeout=8)
        if auto_resp.status_code == 200:
            auto_data = auto_resp.json()
            location_id = extract_location_id(auto_data)
            if location_id:
                return fetch_attractions(location_id, headers, location_name)

    except Exception as e:
        print(f"Travel Advisor Search Error for {location_name}: {e}")

    return get_mock_events(location_name)


def fetch_attractions(location_id, headers, location_name):
    attractions_url = f"https://{RAPIDAPI_HOST}/attractions/list"
    params = {
        "location_id": str(location_id),
        "limit": "8",
        "lang": "en_US",
        "currency": "PKR"
    }

    try:
        resp = requests.get(attractions_url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data if isinstance(data, list) else data.get("data", []) or []
            events = []
            for item in results[:6]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("result_object", {}).get("name")
                    if name:
                        events.append({"name": name.strip(), "distance": "Local attraction"})
            if events:
                return events
    except Exception as e:
        print(f"Attractions fetch error: {e}")

    return get_mock_events(location_name)


def get_mock_events(location_name):
    return [
        {"name": f"{location_name} Cultural Festival", "distance": "Central Area"},
        {"name": "Local Food Street & Night Market", "distance": "Nearby"},
        {"name": "Historical Sites & Museums Tour", "distance": "Walking distance"},
    ]


# ====================== GROQ AI FUNCTIONS ======================

def get_ai_itinerary_adjustment(destination_name, weather_data=None, days=3, budget=None, travel_style=None):
    """Short AI adjustment note based on weather"""
    if not GROQ_API_KEY or GROQ_API_KEY.startswith('gsk_'):
        condition = weather_data.get('condition', 'Clear').lower() if weather_data else 'clear'
        if 'rain' in condition or 'storm' in condition:
            return f"⚠️ Weather Alert: {weather_data.get('description', '')} in {destination_name}. Consider indoor activities."
        return f"🌤️ Good weather expected in {destination_name}. Enjoy your trip!"

    weather_info = ""
    if weather_data:
        weather_info = f"Current weather: {weather_data.get('temp')}°C, {weather_data.get('description')}."

    prompt = f"""
    You are an expert Pakistan travel assistant.

    Destination: {destination_name}
    Duration: {days} days
    {weather_info}
    Budget: {budget if budget else 'Not specified'} PKR
    Travel Style: {travel_style or 'Balanced'}

    Provide a short, helpful AI adjustment note (2-3 sentences max):
    - Weather impact
    - One smart recommendation
    - Positive encouragement

    Friendly and exciting tone for Pakistani travelers.
    Return only the note.
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful travel planner for Pakistan."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=300,
        )
        return chat_completion.choices[0].message.content.strip()

    except Exception as e:
        print(f"Groq Adjustment Error: {e}")
        return f"🌤️ Enjoy your trip to {destination_name}!"


def generate_ai_itinerary(destination_name, days=3, budget=None, travel_style=None, destination_type=None):
    """
    Generate FULL dynamic itinerary using Groq AI.
    Strongly respects user's budget and days.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith('gsk_'):
        return None

    budget_info = f"Total Budget: {budget:,} PKR" if budget else "Moderate budget"

    prompt = f"""
    You are an expert Pakistan travel planner.

    Create a realistic and exciting {days}-day itinerary for **{destination_name}**, Pakistan.

    Important Constraints:
    - Total Budget: {budget_info}
    - Travel Style: {travel_style or 'Balanced'}
    - Destination Type: {destination_type or 'General'}

    Rules:
    - Respect the budget strictly. Suggest affordable/local options if budget is low.
    - Include local Pakistani food, culture, and realistic activities.
    - Mix sightseeing, adventure, relaxation, and meals.
    - Be practical for Pakistani travelers.

    Return **only valid JSON** in this exact format:

    {{
      "summary": "Short engaging overview of the trip",
      "daily_plan": [
        {{
          "day": 1,
          "title": "Day 1: ...",
          "description": "Detailed description of the day",
          "highlight": "Main highlight",
          "activities": ["Activity 1", "Activity 2"],
          "meals": "Breakfast: ..., Lunch: ..., Dinner: ...",
          "tips": "One useful tip"
        }}
      ]
    }}
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional travel planner. Always reply with clean, valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=1600,
        )

        text = response.choices[0].message.content.strip()

        # Clean JSON
        if text.startswith('```json'):
            text = text.replace('```json', '').replace('```', '').strip()
        elif text.startswith('```'):
            text = text.replace('```', '').strip()

        data = json.loads(text)

        if 'daily_plan' not in data:
            data['daily_plan'] = data.get('itinerary', [])

        return data

    except Exception as e:
        print(f"Groq Itinerary Error for {destination_name}: {e}")
        return None


def geocode_location(place_name):
    """Convert place name → lat/lng using OpenStreetMap"""
    url = f"https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name,
        "format": "json",
        "limit": 1
    }

    try:
        res = requests.get(url, params=params, timeout=5, headers={
            "User-Agent": "travel-app"
        })
        data = res.json()

        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except:
        pass

    return None, None