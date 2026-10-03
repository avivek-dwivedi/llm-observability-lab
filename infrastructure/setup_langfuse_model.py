"""Create or UPDATE the Langfuse Model Definition via API (so cost dashboard works).

Usage:
    .venv\\Scripts\\python.exe infrastructure\\setup_langfuse_model.py

Reads the model name and prices from .env:
    GROQ_MODEL=allam-2-7b
    PRICE_INPUT_PER_M=5.00     (USD per 1M input tokens)
    PRICE_OUTPUT_PER_M=15.00   (USD per 1M output tokens)

If a Model Definition for the model already exists with OLD prices, it is
DELETED and re-created with the current prices (Langfuse retroactively
re-prices past traces). Safe to run multiple times.
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Reuse the application's pricing resolution so Langfuse and
# Prometheus/Grafana can NEVER disagree for the same model
# (see docs on resolve_pricing precedence: env override → catalog → None).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from observability.pricing import resolve_pricing  # noqa: E402

LANGFUSE_HOST = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")
LANGFUSE_PK = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SK = os.getenv("LANGFUSE_SECRET_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")


def _request(path: str, method: str = "GET", body: dict | None = None):
    """Basic-auth request against the Langfuse Public API. Returns parsed JSON."""
    auth = base64.b64encode(f"{LANGFUSE_PK}:{LANGFUSE_SK}".encode()).decode()
    req = urllib.request.Request(
        f"{LANGFUSE_HOST}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main():
    if not LANGFUSE_PK or not LANGFUSE_SK:
        print("ERROR: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set in .env")
        return

    cfg = resolve_pricing(MODEL)
    if cfg is None:
        print(f"ERROR: no pricing configured for model '{MODEL}'. "
              f"Set PRICE_INPUT_PER_M / PRICE_OUTPUT_PER_M in .env "
              f"(or add the model to observability.pricing.DEFAULT_CATALOG).")
        return
    print(f"Effective pricing for '{MODEL}' (same source as the app's "
          f"cost estimates): input ${cfg.input_per_m}/M, output ${cfg.output_per_m}/M")

    body = {
        "modelName": MODEL,
        "matchPattern": f"(?i)^({MODEL})$",
        "unit": "TOKENS",
        "inputPrice": cfg.input_per_m / 1_000_000,
        "outputPrice": cfg.output_per_m / 1_000_000,
    }

    # Replace an existing definition whose prices may be stale.
    try:
        existing = _request("/api/public/models")
        models = existing.get("data", existing if isinstance(existing, list) else [])
        for m in models:
            if m.get("modelName") == MODEL:
                print(f"Existing Model Definition for '{MODEL}' found "
                      f"(in=${m.get('inputPrice')}/tok — replacing with current .env prices).")
                _request(f"/api/public/models/{m['id']}", method="DELETE")
                break
    except Exception as e:
        print(f"Note: could not check existing models ({e}) — will POST anyway.")

    try:
        result = _request("/api/public/models", method="POST", body=body)
        print(f"Model Definition created: {result['modelName']}")
        print(f"  Input price:  ${result['inputPrice']}/token (${result['inputPrice'] * 1_000_000}/M)")
        print(f"  Output price: ${result['outputPrice']}/token (${result['outputPrice'] * 1_000_000}/M)")
        print(f"  Match pattern: {result['matchPattern']}")
        print("\nLangfuse cost dashboard will now show real $ amounts.")
        print("(Langfuse retroactively re-prices past traces with the new prices.)")
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"ERROR: HTTP {e.code} — {err}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()