"""Tests unitarios del monitor de data drift (PSI + KS)."""

import json

import numpy as np
import pandas as pd

from ml.monitoring.drift import drift_report, load_logs, psi
from ml.pipeline.modeling import FEATURES, reference_profile


def _frame(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(10, 2, size=(n, len(FEATURES))), columns=FEATURES)
    df["debtor"] = (rng.random(n) < 0.1).astype(int)
    return df


def test_psi_zero_for_identical_distributions() -> None:
    p = [0.2, 0.3, 0.5]
    assert psi(p, p) == 0.0


def test_no_drift_on_same_population() -> None:
    profile = reference_profile(_frame(seed=0))
    report = drift_report(profile, _frame(seed=1))
    assert report["drifted_features"] == []
    assert report["retrain_recommended"] is False


def test_detects_shift_in_continuous_and_binary_features() -> None:
    profile = reference_profile(_frame(seed=0))
    current = _frame(seed=1)
    current["unemployment_rate"] += 4          # choque continuo
    current["debtor"] = 1 - current["debtor"]  # choque en variable binaria
    report = drift_report(profile, current)
    assert "unemployment_rate" in report["drifted_features"]
    assert "debtor" in report["drifted_features"]


def test_load_logs_extracts_features(tmp_path) -> None:
    log = tmp_path / "inference.log"
    records = [
        {"event": "inference", "features": [{"gdp": 1.0}, {"gdp": 2.0}]},
        {"event": "telemetry_disabled"},
    ]
    log.write_text("INFO arranque\n" + "\n".join(json.dumps(r) for r in records), encoding="utf-8")
    df = load_logs(log)
    assert list(df["gdp"]) == [1.0, 2.0]
