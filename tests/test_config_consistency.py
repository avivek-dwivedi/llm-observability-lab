"""Static config checks: Prometheus rules wiring + resource identity."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ── Prometheus rules mount (fix 1) ────────────────────────────────────────

def test_compose_mounts_rules_file():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./infrastructure/prometheus-rules.yml:/etc/prometheus/rules/llm-slo-rules.yml:ro" in compose


def test_prometheus_yml_discovers_mounted_rules():
    prom_yml = (REPO / "infrastructure" / "prometheus.yml").read_text(encoding="utf-8")
    m = re.search(r"rule_files:\s*\n\s*-\s*(\S+)", prom_yml)
    assert m, "rule_files entry missing from prometheus.yml"
    glob = m.group(1)
    assert glob.startswith("/etc/prometheus/rules/")
    # glob pattern must match the compose mount target
    assert glob.endswith("*.yml")
    mount_target = "/etc/prometheus/rules/llm-slo-rules.yml"
    assert mount_target.rstrip(".yml").startswith(glob.rstrip("*.yml")) or glob == "/etc/prometheus/rules/*.yml"


def test_rules_file_exists_and_is_yaml():
    pytest.importorskip("yaml")
    import yaml
    rules = yaml.safe_load((REPO / "infrastructure" / "prometheus-rules.yml").read_text(encoding="utf-8"))
    assert "groups" in rules
    # every rule has record+expr or alert+expr
    for group in rules["groups"]:
        for rule in group["rules"]:
            assert "expr" in rule
            assert "record" in rule or "alert" in rule


def test_prometheus_yml_is_valid_yaml():
    pytest.importorskip("yaml")
    import yaml
    cfg = yaml.safe_load((REPO / "infrastructure" / "prometheus.yml").read_text(encoding="utf-8"))
    assert "global" in cfg and "scrape_configs" in cfg


# ── SLO alert semantics (fixes 2 + 3) ─────────────────────────────────────

@pytest.fixture(scope="module")
def rules_text():
    return (REPO / "infrastructure" / "prometheus-rules.yml").read_text(encoding="utf-8")


def _rule_block(text: str, start_idx: int) -> str:
    """Slice from start_idx up to the next '- record:'/'- alert:' or EOF."""
    next_rule = len(text)
    for marker in ("- record:", "- alert:"):
        j = text.find(marker, start_idx + 1)
        if j != -1:
            next_rule = min(next_rule, j)
    return text[start_idx:next_rule]


def test_latency_populations_are_success_only(rules_text):
    text = rules_text
    for rule in ("llm_obs:p95_latency_1h", "llm_obs:pct_under_4s_1h"):
        i = text.index(rule)
        block = _rule_block(text, i)
        assert 'result="success"' in block, f"{rule} must filter result=success"


def test_breach_alerts_have_min_sample_gate(rules_text):
    text = rules_text
    for alert in ("LLMSuccessRateDegradation", "LLMErrorBudgetConsumption", "LLMLatencyBreach"):
        i = text.index(f"alert: {alert}")
        block = _rule_block(text, i)
        assert ">= 100" in block, f"{alert} must require >= 100 samples (docs/SLOS.md MIN_SAMPLES)"


def test_insufficient_data_alert_present(rules_text):
    assert "alert: LLMInsufficientData" in rules_text


# ── resource identity (fix 6) ─────────────────────────────────────────────

def test_trace_and_metric_resource_use_shared_identity():
    """Trace and metrics resources must come from the shared identity module."""
    instr = (REPO / "observability" / "instrumentation.py").read_text(encoding="utf-8")
    metrics = (REPO / "observability" / "metrics.py").read_text(encoding="utf-8")
    for src in (instr, metrics):
        assert "resource_attributes(" in src
        assert "from observability.identity import" in src
        # no per-module version literals anymore
        assert '"0.1.0"' not in src and '"0.2.0"' not in src
    identity_src = (REPO / "observability" / "identity.py").read_text(encoding="utf-8")
    assert 'SERVICE_VERSION = "0.2.0"' in identity_src
    # single version constant — modules import it instead of defining their own
    assert identity_src.count('SERVICE_VERSION = "') == 1


def test_identity_resource_attributes():
    from observability.identity import resource_attributes, SERVICE_VERSION
    attrs = resource_attributes()
    assert attrs["service.name"]
    assert attrs["service.version"] == SERVICE_VERSION
    assert "deployment.environment" in attrs