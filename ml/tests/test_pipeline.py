"""Tests unitarios del pipeline de entrenamiento/evaluación.

Usan la lógica pura de `modeling.py` (sin MLflow) para ser ejecutables
sin servidor de tracking.
"""

import numpy as np
import pandas as pd

from ml.pipeline.evaluate import decide
from ml.pipeline.modeling import (
    CLASSES,
    FEATURES,
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


def _sample(n_per_class: int = 40, seed: int = 42) -> pd.DataFrame:
    """Dataset sintético con las 36 features: cada clase desplaza la media."""
    rng = np.random.RandomState(seed)
    rows = []
    for cls in range(len(CLASSES)):
        block = rng.normal(loc=cls * 1.5, scale=1.0, size=(n_per_class, len(FEATURES)))
        rows.append(np.column_stack([block, np.full(n_per_class, cls)]))
    df = pd.DataFrame(np.vstack(rows), columns=FEATURES + [TARGET])
    df[TARGET] = df[TARGET].astype(int)
    return df


def test_load_data_reads_csv(tmp_path) -> None:
    csv_path = tmp_path / "dropout.csv"
    _sample(2).to_csv(csv_path, index=False)
    df = load_data(csv_path)
    assert len(df) == 6
    assert TARGET in df.columns


def test_split_data_stratified() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(10), test_size=0.5, random_state=1)
    assert len(X_tr) == 15 and len(X_te) == 15
    # todas las clases siguen presentes en train y test
    assert set(y_tr.unique()) == {0, 1, 2}
    assert set(y_te.unique()) == {0, 1, 2}


def test_train_and_evaluate() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(), test_size=0.25, random_state=0)
    model = train_model(X_tr, y_tr, n_estimators=20, max_depth=4)
    acc = evaluate_model(model, X_te, y_te)
    assert 0.8 <= acc <= 1.0  # clases bien separadas


def test_evaluate_detailed_structure() -> None:
    X_tr, X_te, y_tr, y_te = split_data(_sample(), test_size=0.25, random_state=0)
    report = evaluate_detailed(train_model(X_tr, y_tr, n_estimators=20), X_te, y_te)
    assert set(report["per_class"]) == set(CLASSES)
    assert np.array(report["confusion_matrix"]).sum() == len(y_te)
    assert 0 <= report["f1_macro"] <= 1


def test_check_class_thresholds() -> None:
    report = {"per_class": {"Dropout": {"recall": 0.5}, "Enrolled": {"recall": 0.9}, "Graduate": {"recall": 0.9}}}
    failures = check_class_thresholds(report, {"Dropout": 0.65, "Enrolled": 0.4})
    assert len(failures) == 1 and failures[0].startswith("Dropout")


def test_feature_importance_sorted() -> None:
    X_tr, _, y_tr, _ = split_data(_sample())
    pairs = feature_importance(train_model(X_tr, y_tr, n_estimators=10), top=5)
    assert len(pairs) == 5
    assert [p[1] for p in pairs] == sorted((p[1] for p in pairs), reverse=True)


def test_reference_profile_handles_binary_features() -> None:
    X = _sample()[FEATURES].copy()
    X["debtor"] = [0, 1] * (len(X) // 2)
    profile = reference_profile(X)
    assert len(profile["debtor"]["proportions"]) == 2
    assert abs(sum(profile["gdp"]["proportions"]) - 1) < 1e-9


def test_decide_rules() -> None:
    per_class_ok = {c: {"recall": 0.9} for c in CLASSES}
    cand = {"accuracy": 0.75, "f1_macro": 0.70, "per_class": per_class_ok}
    thresholds = {"Dropout": 0.65}
    assert decide(cand, None, 0.70, thresholds)["deploy"] is True
    # peor que producción en F1 macro -> no se despliega
    assert decide(cand, {"f1_macro": 0.75}, 0.70, thresholds)["deploy"] is False
    # bajo el baseline global
    assert decide({**cand, "accuracy": 0.6}, None, 0.70, thresholds)["deploy"] is False
    # recall de Dropout bajo el umbral
    bad = {**cand, "per_class": {**per_class_ok, "Dropout": {"recall": 0.5}}}
    assert decide(bad, None, 0.70, thresholds)["deploy"] is False
