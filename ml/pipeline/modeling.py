"""Lógica pura de entrenamiento/evaluación (sin dependencia de MLflow).

Separada de `train.py` para que pueda probarse unitariamente sin
necesidad de un servidor de tracking de MLflow.

Modelo: RandomForest binario sobre el dataset ENAPE 2021
(`ml/data/enape.csv`, generado por `ml/data/load_enape.py`): predice si un
estudiante de la cohorte 2021-2022 abandonará (no se reinscribe).

`FEATURES` es el contrato público de 18 variables (el orden que acepta el
endpoint). El modelo se entrena con `MODEL_FEATURES`, que excluye
`max_nivel_esp` y `entr_diagnost`: en ENAPE solo se preguntan a quien sigue
inscrito, por lo que su código 0 reproduce la etiqueta (ROC-AUC ~1.0).
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from ml.data.load_enape import CLASSES, FEATURES, LABEL, LEAKY_FEATURES, TARGET

# Features efectivamente usadas por el modelo (contrato menos fugas)
MODEL_FEATURES = [column for column in FEATURES if column not in LEAKY_FEATURES]

# Umbral mínimo de recall de la clase de negocio. `Abandona` es la clase que
# Bienestar Universitario necesita detectar; con el desbalance 6,5/93,5 un
# modelo sin umbral la ignoraría.
DEFAULT_CLASS_THRESHOLDS = {"Abandona": 0.60}


def load_data(path: Path) -> pd.DataFrame:
    """Lee el dataset desde un CSV."""
    return pd.read_csv(path)


def split_data(data: pd.DataFrame, test_size: float = 0.2, random_state: int = 42):
    """Divide en train/test estratificado usando las features del modelo."""
    X = data[MODEL_FEATURES]
    y = data[TARGET]
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)


def train_model(
    X_train,
    y_train,
    n_estimators: int = 300,
    max_depth: int | None = 10,
    min_samples_leaf: int = 3,
    class_weight: str | None = "balanced_subsample",
):
    """Entrena un RandomForestClassifier binario.

    Los valores por defecto son los del pipeline anterior (300 árboles,
    profundidad 10, hoja mínima 3). `class_weight="balanced_subsample"`
    compensa el fuerte desbalance (Abandona es ~6,5 %) y prioriza el recall.
    """
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight=class_weight,
        random_state=42,
        n_jobs=-1,
    ).fit(X_train, y_train)


def evaluate_model(model, X_test, y_test) -> float:
    """Evalúa en test y devuelve accuracy."""
    y_pred = model.predict(X_test)
    return float(accuracy_score(y_test, y_pred))


def positive_probabilities(model, X_test) -> np.ndarray:
    """P(Abandona) para cada fila, usando la columna de la clase positiva."""
    proba = model.predict_proba(X_test)
    classes = list(getattr(model, "classes_", [0, 1]))
    positive = 1
    if positive not in classes:
        positive = classes[-1]
    return np.asarray(proba)[:, classes.index(positive)]


def evaluate_detailed(model, X_test, y_test) -> dict:
    """Métricas completas: accuracy, F1 macro, ROC-AUC, PR-AUC, por clase y matriz."""
    y_pred = model.predict(X_test)
    labels = list(range(len(CLASSES)))
    prec, rec, f1, support = precision_recall_fscore_support(
        y_test, y_pred, labels=labels, zero_division=0
    )
    per_class = {
        name: {
            "precision": float(prec[i]),
            "recall": float(rec[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, name in enumerate(CLASSES)
    }
    proba = positive_probabilities(model, X_test)
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro")),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "pr_auc": float(average_precision_score(y_test, proba)),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=labels).tolist(),
    }


def check_class_thresholds(report: dict, thresholds: dict | None = None) -> list[str]:
    """Devuelve las clases cuyo recall queda por debajo del umbral (lista vacía = OK)."""
    thresholds = DEFAULT_CLASS_THRESHOLDS if thresholds is None else thresholds
    failures = []
    for name, minimum in thresholds.items():
        recall = report["per_class"][name]["recall"]
        if recall < minimum:
            failures.append(f"{name}: recall {recall:.3f} < {minimum:.2f}")
    return failures


def feature_importance(model, top: int | None = None) -> list[tuple[str, float]]:
    """Importancia (Gini) de cada feature del modelo, ordenada de mayor a menor."""
    pairs = sorted(
        zip(MODEL_FEATURES, model.feature_importances_), key=lambda p: p[1], reverse=True
    )
    pairs = [(name, float(value)) for name, value in pairs]
    return pairs[:top] if top else pairs


def reference_profile(X: pd.DataFrame, bins: int = 10) -> dict:
    """Perfil de referencia de cada feature para detectar data drift.

    Guarda los bordes de los cuantiles y la proporción de datos en cada
    bin; `ml/monitoring/drift.py` compara contra este perfil (PSI + KS).
    """
    profile = {}
    for col in MODEL_FEATURES:
        values = X[col].to_numpy(dtype=float)
        uniques = np.unique(values)
        if len(uniques) <= 20:
            # Variable discreta/binaria: un bin por valor (los cuantiles colapsarían)
            mids = (uniques[:-1] + uniques[1:]) / 2
            edges = np.concatenate([[uniques[0] - 0.5], mids, [uniques[-1] + 0.5]])
        else:
            edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))
        counts, _ = np.histogram(values, bins=edges)
        profile[col] = {
            "edges": edges.tolist(),
            "proportions": (counts / counts.sum()).tolist(),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "sample": values[:: max(1, len(values) // 500)].tolist(),
        }
    return profile


def save_model(model, path: Path) -> None:
    """Guarda el modelo con joblib."""
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path / "model.pkl")


__all__ = [
    "CLASSES",
    "DEFAULT_CLASS_THRESHOLDS",
    "FEATURES",
    "LABEL",
    "MODEL_FEATURES",
    "TARGET",
    "check_class_thresholds",
    "evaluate_detailed",
    "evaluate_model",
    "feature_importance",
    "load_data",
    "positive_probabilities",
    "reference_profile",
    "save_model",
    "split_data",
    "train_model",
]
