"""Create Langfuse Model Definition via API (so cost dashboard works automatically).

Usage:
    .venv\\Scripts\\python.exe infrastructure\\setup_langfuse_model.py
"""

import base64
import json
import os
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

LANGFUSE_HOST = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")
LANGFUSE_PK = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SK = os.getenv("LANGFUSE_SECRET_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")
INPUT_PRICE = 0.000005   # $5/M tokens
OUTPUT_PRICE = 0.000015  # $15/M tokens


def main():
    if not LANGFUSE_PK or not LANGFUSE_SK:
        print("ERROR: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set in .env")
        return

    auth = base64.b64encode(f"{LANGFUSE_PK}:{LANGFUSE_SK}".encode()).decode()
    body = json.dumps({
        "modelName": MODEL,
        "matchPattern": f"(?i)^({MODEL})$",
        "unit": "TOKENS",
        "inputPrice": INPUT_PRICE,
        "outputPrice": OUTPUT_PRICE,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{LANGFUSE_HOST}/api/public/models",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print(f"Model Definition created: {result['modelName']}")
            print(f"  Input price:  ${result['inputPrice']}/token (${result['inputPrice']*1_000_000}/M)")
            print(f"  Output price: ${result['outputPrice']}/token (${result['outputPrice']*1_000_000}/M)")
            print(f"  Match pattern: {result['matchPattern']}")
            print(f"\nLangfuse cost dashboard will now show real $ amounts.")
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        if "already exists" in err.lower() or "unique" in err.lower():
            print(f"Model Definition for '{MODEL}' already exists — skipping.")
        else:
            print(f"ERROR: HTTP {e.code} — {err}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()