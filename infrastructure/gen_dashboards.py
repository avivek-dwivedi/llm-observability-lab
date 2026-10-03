"""Generate 3 Grafana dashboards with identical panels but different workflow filters."""

import json
import os

DIR = os.path.join(os.path.dirname(__file__), "grafana", "dashboards")

# Panel template — 'W' will be replaced with the actual workflow name
PANELS_TEMPLATE = [
    {"id": 1, "type": "stat", "title": "Total Requests",
     "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_requests_total{workflow="W"})', "refId": "A"}],
     "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "blue", "value": None}]}}}},

    {"id": 2, "type": "stat", "title": "Success Rate",
     "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_requests_total{workflow="W",result="success"}) / clamp_min(sum(llm_obs_llm_requests_total{workflow="W"}), 1)', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "percentunit", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 0.90}, {"color": "green", "value": 0.99}]}}}},

    {"id": 3, "type": "stat", "title": "Error Count",
     "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_requests_total{workflow="W",result!="success"})', "refId": "A"}],
     "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": 0}, {"color": "red", "value": 1}]}}}},

    {"id": 4, "type": "stat", "title": "Error Budget",
     "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": '1 - (sum(llm_obs_llm_requests_total{workflow="W"}) - sum(llm_obs_llm_requests_total{workflow="W",result="success"})) / clamp_min(sum(llm_obs_llm_requests_total{workflow="W"}) * 0.005, 1)', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "percentunit", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 0.2}, {"color": "green", "value": 0.5}]}}}},

    {"id": 5, "type": "stat", "title": "P50 Latency",
     "gridPos": {"h": 4, "w": 6, "x": 0, "y": 4},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'histogram_quantile(0.50, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "s", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 4}]}}}},

    {"id": 6, "type": "stat", "title": "P90 Latency",
     "gridPos": {"h": 4, "w": 6, "x": 6, "y": 4},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'histogram_quantile(0.90, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "s", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 3}, {"color": "red", "value": 4}]}}}},

    {"id": 7, "type": "stat", "title": "P95 Latency",
     "gridPos": {"h": 4, "w": 6, "x": 12, "y": 4},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'histogram_quantile(0.95, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "s", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 4}]}}}},

    {"id": 8, "type": "stat", "title": "P99 Latency",
     "gridPos": {"h": 4, "w": 6, "x": 18, "y": 4},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'histogram_quantile(0.99, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "s", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 5}, {"color": "red", "value": 10}]}}}},

    {"id": 10, "type": "stat", "title": "Avg Latency",
     "gridPos": {"h": 4, "w": 6, "x": 0, "y": 8},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_request_duration_seconds_sum{workflow="W"}) / clamp_min(sum(llm_obs_llm_request_duration_seconds_count{workflow="W"}), 1)', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "s", "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 2}, {"color": "red", "value": 4}]}}}},

    {"id": 11, "type": "stat", "title": "Estimated Cost",
     "gridPos": {"h": 4, "w": 6, "x": 6, "y": 8},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_estimated_cost_usd_USD_total{workflow="W"})', "refId": "A"}],
     "fieldConfig": {"defaults": {"unit": "currencyUSD", "decimals": 2, "color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 10}]}}}},

    {"id": 12, "type": "stat", "title": "Total Tokens",
     "gridPos": {"h": 4, "w": 6, "x": 12, "y": 8},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_tokens_total{workflow="W"})', "refId": "A"}],
     "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "blue", "value": None}]}}}},

    {"id": 13, "type": "stat", "title": "Failed Retries",
     "gridPos": {"h": 4, "w": 6, "x": 18, "y": 8},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_api_attempts_total{workflow="W",outcome!="success"})', "refId": "A"}],
     "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": 0}, {"color": "yellow", "value": 5}, {"color": "red", "value": 20}]}}}},

    {"id": 20, "type": "timeseries", "title": "Request Rate (Success vs Errors)",
     "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum by (result) (llm_obs_llm_requests_total{workflow="W"})', "refId": "A", "legendFormat": "{{result}}"}],
     "fieldConfig": {"defaults": {"unit": "short"}}},

    {"id": 21, "type": "timeseries", "title": "Latency P50 / P90 / P95 / P99",
     "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [
       {"expr": 'histogram_quantile(0.50, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "A", "legendFormat": "P50"},
       {"expr": 'histogram_quantile(0.90, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "B", "legendFormat": "P90"},
       {"expr": 'histogram_quantile(0.95, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "C", "legendFormat": "P95"},
       {"expr": 'histogram_quantile(0.99, sum by (le) (llm_obs_llm_request_duration_seconds_bucket{workflow="W"}))', "refId": "D", "legendFormat": "P99"}
     ],
     "fieldConfig": {"defaults": {"unit": "s"}}},

    {"id": 22, "type": "timeseries", "title": "Cost Over Time",
     "gridPos": {"h": 8, "w": 12, "x": 0, "y": 20},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum(llm_obs_llm_estimated_cost_usd_USD_total{workflow="W"})', "refId": "A", "legendFormat": "cost"}],
     "fieldConfig": {"defaults": {"unit": "currencyUSD"}}},

    {"id": 23, "type": "timeseries", "title": "Token Consumption (Input vs Output)",
     "gridPos": {"h": 8, "w": 12, "x": 12, "y": 20},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [
       {"expr": 'sum(llm_obs_llm_tokens_total{workflow="W",token_type="input"})', "refId": "A", "legendFormat": "Input"},
       {"expr": 'sum(llm_obs_llm_tokens_total{workflow="W",token_type="output"})', "refId": "B", "legendFormat": "Output"}
     ],
     "fieldConfig": {"defaults": {"unit": "short"}}},

    {"id": 24, "type": "timeseries", "title": "API Attempts vs Successful",
     "gridPos": {"h": 8, "w": 12, "x": 0, "y": 28},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [
       {"expr": 'sum(llm_obs_llm_api_attempts_total{workflow="W"})', "refId": "A", "legendFormat": "Total attempts"},
       {"expr": 'sum(llm_obs_llm_requests_total{workflow="W",result="success"})', "refId": "B", "legendFormat": "Successful"},
       {"expr": 'sum(llm_obs_llm_api_attempts_total{workflow="W",outcome!="success"})', "refId": "C", "legendFormat": "Failed attempts"}
     ],
     "fieldConfig": {"defaults": {"unit": "short"}}},

    {"id": 25, "type": "timeseries", "title": "Errors by Type",
     "gridPos": {"h": 8, "w": 12, "x": 12, "y": 28},
     "datasource": {"type": "prometheus", "uid": "prometheus"},
     "targets": [{"expr": 'sum by (result) (llm_obs_llm_requests_total{workflow="W",result!="success"})', "refId": "A", "legendFormat": "{{result}}"}],
     "fieldConfig": {"defaults": {"unit": "short"}}},
]

DASHBOARDS = [
    ("1_normal.json",         "1. Normal",         "d1-normal",   "normal"),
    ("2_llm_degraded.json",   "2. LLM Degraded",   "d2-degraded", "llm_degraded"),
    ("3_system_failure.json", "3. System Failure", "d3-failure",  "system_failure"),
]


def main():
    os.makedirs(DIR, exist_ok=True)
    for filename, title, uid, workflow in DASHBOARDS:
        panels = []
        for p in PANELS_TEMPLATE:
            p2 = json.loads(json.dumps(p))
            if "targets" in p2:
                for t in p2["targets"]:
                    if "expr" in t:
                        t["expr"] = t["expr"].replace('"W"', f'"{workflow}"')
            panels.append(p2)

        dash = {
            "title": title,
            "uid": uid,
            "tags": ["llm", "sre"],
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 1,
            "refresh": "10s",
            "time": {"from": "now-1h", "to": "now"},
            "panels": panels,
        }
        path = os.path.join(DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dash, f, indent=2)
        print(f"Created {filename}  uid={uid}  workflow={workflow}  panels={len(panels)}")


if __name__ == "__main__":
    main()