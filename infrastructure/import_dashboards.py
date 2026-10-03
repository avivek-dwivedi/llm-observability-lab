"""Import Grafana dashboards via the API (more reliable than file provisioning).

Usage:
    .venv\\Scripts\\python.exe infrastructure\\import_dashboards.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASS = os.getenv("GRAFANA_PASS", "admin")
DASHBOARDS_DIR = os.path.join(os.path.dirname(__file__), "grafana", "dashboards")

import base64
auth = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()


def import_dashboard(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        dashboard = json.load(f)

    body = json.dumps({
        "dashboard": dashboard,
        "overwrite": True,
        "folderId": 0,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/db",
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
            return result
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "message": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}


def main():
    if not os.path.isdir(DASHBOARDS_DIR):
        print(f"ERROR: dashboards dir not found: {DASHBOARDS_DIR}")
        sys.exit(1)

    files = [f for f in os.listdir(DASHBOARDS_DIR) if f.endswith(".json")]
    if not files:
        print(f"ERROR: no .json files in {DASHBOARDS_DIR}")
        sys.exit(1)

    print(f"Importing {len(files)} dashboard(s) to {GRAFANA_URL}")
    print("=" * 50)

    for filename in sorted(files):
        filepath = os.path.join(DASHBOARDS_DIR, filename)
        print(f"  {filename} ... ", end="", flush=True)
        result = import_dashboard(filepath)
        if "error" in result:
            print(f"FAILED: {result['error']} — {result.get('message', '')}")
        else:
            print(f"OK (uid={result.get('uid')}, version={result.get('version')})")

    print("=" * 50)
    print("Done. Open Grafana:")
    for f in sorted(files):
        with open(os.path.join(DASHBOARDS_DIR, f), "r") as fh:
            d = json.load(fh)
            uid = d.get("uid", "")
            slug = d.get("title", "").lower().replace(" ", "-")
            print(f"  {GRAFANA_URL}/d/{uid}/{slug}")


if __name__ == "__main__":
    main()