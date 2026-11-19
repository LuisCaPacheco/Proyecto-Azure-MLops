"""Tests unitarios del pipeline de entrenamiento/evaluación.

Usan la lógica pura de `modeling.py` (sin MLflow) para ser ejecutables
sin servidor de tracking.
"""

import numpy as np
import pandas as pd

from ml.pipeline.evaluate import decide, get_production_metrics
from ml.pipeline.promote import promote
from ml.pipeline.modeling import (
    CLASSES,
    DEFAULT_CLASS_THRESHOLDS,
    MODEL_FEATURES,
    TARGET,
    check_class_thresholds,
    evaluate_detailed,
    evaluate_model,
    feature_importance,
    load_data,
    reference_profile,
    split_data,
    train_model,
)


def _sample(n_per_class: int = 60, seed: int = 42) -> pd.DataFrame:
    """Dataset sintético binario: cada clase desplaza la media."""
    rng = np.random.RandomState(seed)
    rows = []
    for cls in range(len(CLASSES)):
        block = rng.normal(loc=cls * 2.0, scale=1.0, size=(n_per_class, len(MODEL_FEATURES)))
        rows.append(np.column_stack([block, np.full(n_per_class, cls)]))
    df = pd.DataFrame(np.vstack(rows), columns=MODEL_FEATURES + [TARGET])
    df[TARGET] = df[TARGET].astype(int)
    return df


def test_load_data_reads_csv(tmp_path) -> None:
    csv_path = tmp_path / "enape.csv"
    _sample(2).to_csv(csv_path, index=False)
    df = load_data(csv_path)
    assert len(df) == 4
    assert TARGET in df.columns


def test_split_data_stratified() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(10), test_size=0.5, random_state=1)
    assert len(X_tr) == 10 and len(X_te) == 10
    # ambas clases siguen presentes en train y test
    assert set(y_tr.unique()) == {0, 1}
    assert set(y_te.unique()) == {0, 1}
    assert list(X_tr.columns) == MODEL_FEATURES


def test_train_and_evaluate() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(), test_size=0.25, random_state=0)
    model = train_model(X_tr, y_tr, n_estimators=20, max_depth=4)
    acc = evaluate_model(model, X_te, y_te)
    assert 0.9 <= acc <= 1.0  # clases bien separadas


def test_evaluate_detailed_structure() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(), test_size=0.25, random_state=0)
    report = evaluate_detailed(train_model(X_tr, y_tr, n_estimators=20), X_te, y_te)
    assert set(report["per_class"]) == set(CLASSES)
    assert np.array(report["confusion_matrix"]).sum() == len(y_te)
    assert 0 <= report["f1_macro"] <= 1
    assert 0 <= report["roc_auc"] <= 1
    assert 0 <= report["pr_auc"] <= 1


def test_check_class_thresholds() -> None:
    report = {"per_class": {"Continua": {"recall": 0.9}, "Abandona": {"recall": 0.5}}}
    failures = check_class_thresholds(report, {"Abandona": 0.6})
    assert len(failures) == 1 and failures[0].startswith("Abandona")


def test_feature_importance_sorted() -> None:
    X_tr, _, y_tr, _ = split_data(_sample())
    pairs = feature_importance(train_model(X_tr, y_tr, n_estimators=10), top=5)
    assert len(pairs) == 5
    assert [p[1] for p in pairs] == sorted((p[1] for p in pairs), reverse=True)


def test_reference_profile_handles_binary_features() -> None:
    X = _sample()[MODEL_FEATURES].copy()
    X["internet_f"] = ([0, 1] * (len(X) // 2 + 1))[: len(X)]
    profile = reference_profile(X)
    assert len(profile["internet_f"]["proportions"]) == 2
    assert abs(sum(profile["edad"]["proportions"]) - 1) < 1e-9


def _candidate(**overrides) -> dict:
    base = {
        "accuracy": 0.90,
        "f1_macro": 0.70,
        "roc_auc": 0.88,
        "pr_auc": 0.50,
        "per_class": {"Continua": {"recall": 0.95}, "Abandona": {"recall": 0.70}},
    }
    base.update(overrides)
    return base


def test_registry_comparison_fails_closed_without_tracking_uri(monkeypatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI"):
        get_production_metrics("enape-abandono")


def test_decide_requires_production_registry_metrics() -> None:
    result = decide(_candidate(), production=None)
    assert result["deploy"] is False
    assert result["beats_production_pr_auc"] is False


def test_decide_rejects_production_record_without_pr_auc() -> None:
    result = decide(_candidate(), production={"version": "1"})
    assert result["deploy"] is False
    assert result["beats_production_pr_auc"] is False


def test_decide_accepts_candidate_above_thresholds() -> None:
    result = decide(_candidate(), production={"version": "1", "pr_auc": 0.40})
    assert result["deploy"] is True
    assert result["meets_pr_auc"] and result["meets_recall_abandona"]


def test_decide_rejects_low_pr_auc() -> None:
    result = decide(_candidate(pr_auc=0.20), production={"version": "1", "pr_auc": 0.40})
    assert result["deploy"] is False and result["meets_pr_auc"] is False


def test_decide_rejects_low_recall() -> None:
    cand = _candidate(per_class={"Continua": {"recall": 0.95}, "Abandona": {"recall": 0.40}})
    result = decide(cand, production={"version": "1", "pr_auc": 0.40})
    assert result["deploy"] is False and result["meets_recall_abandona"] is False


def test_decide_requires_missing_metrics() -> None:
    production = {"version": "1", "pr_auc": 0.40}
    assert decide(_candidate(pr_auc=None), production=production)["deploy"] is False
    assert decide(_candidate(per_class={}), production=production)["deploy"] is False


def test_decide_blocks_pr_auc_regression() -> None:
    production = {"version": "1", "pr_auc": 0.60}
    result = decide(_candidate(pr_auc=0.50), production)
    assert result["beats_production_pr_auc"] is False and result["deploy"] is False
    # dentro de la tolerancia (0.005) sí se acepta
    edge = decide(_candidate(pr_auc=0.596), production)
    assert edge["deploy"] is True


def test_decide_uses_default_class_thresholds() -> None:
    assert DEFAULT_CLASS_THRESHOLDS == {"Abandona": 0.60}


def test_decide_rejects_candidate_already_in_production() -> None:
    cand = _candidate(registry={"version": "4"})
    result = decide(cand, {"version": "4", "pr_auc": 0.40})
    assert result["same_version_as_production"] is True and result["deploy"] is False
    other = decide(cand, {"version": "3", "pr_auc": 0.40})
    assert other["candidate_version"] == "4" and other["deploy"] is True


class _FakeVersion:
    def __init__(self, version: str) -> None:
        self.version = version


class _FakeRegistry:
    """Doble mínimo de MlflowClient: guarda el stage de cada versión."""

    def __init__(self, stages: dict) -> None:
        self.stages = dict(stages)
        self.aliases = {}

    def search_model_versions(self, _filter: str):
        return [_FakeVersion(v) for v, s in self.stages.items() if s == "Production"]

    def transition_model_version_stage(self, name: str, version: str, stage: str) -> None:
        self.stages[str(version)] = stage

    def set_model_version_tag(self, name: str, version: str, key: str, value: str) -> None:
        pass

    def set_registered_model_alias(self, name: str, alias: str, version: str) -> None:
        self.aliases[alias] = str(version)


def test_promote_archives_previous_production() -> None:
    registry = _FakeRegistry({"1": "Archived", "2": "Production", "3": "Staging"})
    result = promote(registry, "enape-abandono", "3")
    assert registry.stages == {"1": "Archived", "2": "Archived", "3": "Production"}
    assert registry.aliases["production"] == "3"
    assert result == {"model_name": "enape-abandono", "promoted": "3", "archived": ["2"]}


def test_promote_is_idempotent() -> None:
    registry = _FakeRegistry({"3": "Production"})
    assert promote(registry, "enape-abandono", "3")["archived"] == []
    assert registry.stages == {"3": "Production"}
