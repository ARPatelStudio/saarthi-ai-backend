import requests
import logging
import datetime
import pytz

logger = logging.getLogger(__name__)

def get_live_weather(location: str, api_key: str):
    if not api_key: 
        return "Weather API key missing hai boss."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric&lang=hi"
        response = requests.get(url, timeout=8).json()
        if response.get("cod") != 200: 
            return f"Sorry boss, mujhe {location} ka exact weather data nahi mil pa raha."
        return f"Live Update: {location} mein abhi temp {response['main']['temp']}°C hai aur mausam '{response['weather'][0]['description']}' jaisa hai."
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "Weather API mein thoda glitch aaya boss."

def analyze_weather_threats(lat: float, lon: float, api_key: str):
    """Returns: city_name, weather_desc, alerts_detected (list)"""
    city_name = "Unknown Area"
    weather_desc = "clear"
    alerts_detected = []

    if not api_key:
        return city_name, weather_desc, alerts_detected

    try:
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=hi"
        weather_res = requests.get(weather_url, timeout=8).json()

        if weather_res.get("cod") == 200:
            city_name = weather_res.get("name", "Unknown Area")
            weather_desc = weather_res["weather"][0]["description"].lower()
            weather_id = weather_res["weather"][0]["id"]

            # 🌪️ Universal Extreme Weather Detection
            if (200 <= weather_id <= 299): alerts_detected.append("thunderstorm (bhaari toofan)")
            elif (500 <= weather_id <= 511) or weather_id in [522, 531]: alerts_detected.append("bhaari baarish aur badh (flood)")
            elif (600 <= weather_id <= 699): alerts_detected.append("heavy snowfall ya barfbaari")
            elif weather_id == 781: alerts_detected.append("TORNADO ALERT")
            elif weather_id == 762: alerts_detected.append("Volcanic ash")
    except Exception as e:
        logger.error(f"Weather Threat API Error: {e}")

    return city_name, weather_desc, alerts_detected
