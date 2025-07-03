import requests
from datetime import datetime
from zoho_auth import get_access_token
import json
import os

# Replace with your actual Zoho credentials and endpoints
ACCESS_TOKEN = get_access_token()
ORG_ID = "60033879553"
BASE_URL = "https://www.zohoapis.in/books/v3"

HEADERS = {
    "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

CACHE_FILE = "items_cache.json"

def fetch_items():
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Check if cache file exists
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cached_data = json.load(f)
            if cached_data.get("date") == today_str:
                print("✅ Using cached items")
                return cached_data.get("items", {})

    # Fetch from API if no valid cache
    url = f"{BASE_URL}/items?organization_id={ORG_ID}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    items = data.get("items", [])

    item_dict = {item['name']: item for item in items}

    # Save to cache
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "date": today_str,
            "items": item_dict
        }, f)

    print("🔄 Fetched items from Zoho and updated cache")
    return item_dict

def create_estimate(estimate_data):
    url = f"{BASE_URL}/estimates?organization_id={ORG_ID}"
    response = requests.post(url, headers=HEADERS, json=estimate_data)
    return response.json()

def fetch_estimates():
    url = f"{BASE_URL}/estimates?organization_id={ORG_ID}&sort_column=estimate_number&sort_order=D"
    response = requests.get(url, headers=HEADERS)
    # print(response.json())
    return response.json().get("estimates", [])

def download_estimate_pdf(estimate_id):
    url = f"{BASE_URL}/estimates/{estimate_id}?organization_id={ORG_ID}&accept=pdf"
    response = requests.get(url, headers=HEADERS)
    return response.content
