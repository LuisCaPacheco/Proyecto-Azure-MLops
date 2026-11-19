"""Tests unitarios del monitor de data drift (PSI + KS)."""

import json

import numpy as np
import pandas as pd

from ml.monitoring.drift import drift_report, load_logs, psi
from ml.pipeline.modeling import MODEL_FEATURES, reference_profile


def _frame(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(10, 2, size=(n, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
    df["internet_f"] = (rng.random(n) < 0.1).astype(int)
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
    current["edad"] += 4                 # choque continuo
    current["internet_f"] = 1 - current["internet_f"]  # choque en variable binaria
    report = drift_report(profile, current)
    assert "edad" in report["drifted_features"]
    assert "internet_f" in report["drifted_features"]


def test_load_logs_extracts_features(tmp_path) -> None:
    log = tmp_path / "inference.log"
    records = [
        {"event": "inference", "features": [{"edad": 1.0}, {"edad": 2.0}]},
        {"event": "telemetry_disabled"},
    ]
    log.write_text("INFO arranque\n" + "\n".join(json.dumps(r) for r in records), encoding="utf-8")
    df = load_logs(log)
    assert list(df["edad"]) == [1.0, 2.0]
