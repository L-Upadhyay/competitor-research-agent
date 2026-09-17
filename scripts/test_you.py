# Quick manual check that the You.com API key and search endpoint work.

import os
import sys
from pathlib import Path

# Let this script find the "agent" folder in the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import search_you  # noqa: E402


def show(result):
    """Print a search result in a readable way."""
    print(f"ok: {result['ok']}")
    if not result["ok"]:
        print(f"error: {result['error']}")
        return
    print(f"web results: {len(result['web'])}, news results: {len(result['news'])}")
    for item in result["web"] + result["news"]:
        print(f"- {item['title']}\n  {item['url']}\n  {item['snippet'][:120]}...")


def main():
    if not os.getenv("YDC_API_KEY") and not Path(".env").exists():
        sys.exit("YDC_API_KEY is missing. Add it to your .env file (see .env.example).")

    print("=== a) normal search ===")
    show(search_you("Brex corporate card pricing"))

    print("\n=== b) recent news search ===")
    show(search_you("Brex news", recent_only=True))

    print("\n=== c) failure with a fake API key ===")
    real_key = os.environ.get("YDC_API_KEY")
    os.environ["YDC_API_KEY"] = "fake-key-for-testing"
    try:
        show(search_you("Brex corporate card pricing"))
    finally:
        # Put the real key back no matter what happened.
        if real_key is None:
            os.environ.pop("YDC_API_KEY", None)
        else:
            os.environ["YDC_API_KEY"] = real_key


if __name__ == "__main__":
    main()
