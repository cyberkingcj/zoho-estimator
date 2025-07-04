import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CACHE_FILE = Path("token_cache.json")

CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

def save_token_cache(access_token, expires_in):
    cache = {
        "access_token": access_token,
        "expiry": int(time.time()) + expires_in - 60  # 60s buffer
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def load_token_cache():
    if not CACHE_FILE.exists():
        return None
    with open(CACHE_FILE, "r") as f:
        return json.load(f)

def refresh_access_token():
    url = "https://accounts.zoho.in/oauth/v2/token"
    params = {
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, params=params)
    if response.status_code == 200:
        data = response.json()
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        save_token_cache(access_token, expires_in)
        return access_token
    else:
        raise Exception(f"Failed to refresh token: {response.text}")

def get_access_token():
    cache = load_token_cache()
    if cache and time.time() < cache["expiry"]:
        print("Using cached access token")
        print(f"Token expires at: {time.ctime(cache['expiry'])}")
        return cache["access_token"]
    else:
        print("Refreshing access token")
        print(f"Current time: {time.ctime(time.time())}")
        return refresh_access_token()
