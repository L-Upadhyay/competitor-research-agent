# Quick manual check that the You.com API key and search endpoint work.
import os
import sys

import requests
from dotenv import load_dotenv

SEARCH_URL = "https://api.you.com/v1/search"
QUERY = "Ramp corporate card competitors"


def main():
    load_dotenv()
    api_key = os.getenv("YDC_API_KEY")
    if not api_key:
        sys.exit("YDC_API_KEY is missing. Add it to your .env file (see .env.example).")

    response = requests.get(
        SEARCH_URL,
        headers={"X-API-Key": api_key},
        params={"query": QUERY, "count": 3},
        timeout=20,
    )
    print(f"Status code: {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        sys.exit(f"Response was not JSON:\n{response.text[:500]}")

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, dict) or "web" not in results:
        print("Unexpected response shape.")
        if isinstance(data, dict):
            print(f"Top-level keys: {list(data.keys())}")
        else:
            print(f"Top-level type: {type(data).__name__}")
        sys.exit(1)

    print("\nWeb results:")
    for i, item in enumerate(results.get("web", []), start=1):
        print(f"{i}. {item.get('title')}\n   {item.get('url')}")

    print(f"\nNews results: {len(results.get('news', []))}")


if __name__ == "__main__":
    main()
