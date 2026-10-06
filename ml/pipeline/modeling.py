"""Lógica pura de entrenamiento/evaluación (sin dependencia de MLflow).

Separada de `train.py` para que pueda probarse unitariamente sin
necesidad de un servidor de tracking de MLflow.

Modelo: RandomForest multiclase sobre el dataset UCI de deserción
(`ml/data/dropout.csv`, generado por `ml/data/load_data.py`).
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split

# 36 características del dataset (orden fijo: es el orden que espera el endpoint)
FEATURES = [
    "marital_status",
    "application_mode",
    "application_order",
    "course",
    "daytime_evening_attendance",
    "previous_qualification",
    "previous_qualification_grade",
    "nationality",
    "mothers_qualification",
    "fathers_qualification",
    "mothers_occupation",
    "fathers_occupation",
    "admission_grade",
    "displaced",
    "educational_special_needs",
    "debtor",
    "tuition_fees_up_to_date",
    "gender",
    "scholarship_holder",
    "age_at_enrollment",
    "international",
    "curricular_units_1st_sem_credited",
    "curricular_units_1st_sem_enrolled",
    "curricular_units_1st_sem_evaluations",
    "curricular_units_1st_sem_approved",
    "curricular_units_1st_sem_grade",
    "curricular_units_1st_sem_without_evaluations",
    "curricular_units_2nd_sem_credited",
    "curricular_units_2nd_sem_enrolled",
    "curricular_units_2nd_sem_evaluations",
    "curricular_units_2nd_sem_approved",
    "curricular_units_2nd_sem_grade",
    "curricular_units_2nd_sem_without_evaluations",
    "unemployment_rate",
    "inflation_rate",
    "gdp",
]
TARGET = "target"
CLASSES = ["Dropout", "Enrolled", "Graduate"]

# Umbrales mínimos de recall por clase (regresión del modelo, no solo global).
# Dropout es la clase de negocio: no podemos dejar de detectar desertores, y
# Enrolled no puede quedar ignorada (un modelo sin balanceo la detecta ~30 %).
DEFAULT_CLASS_THRESHOLDS = {"Dropout": 0.65, "Enrolled": 0.40, "Graduate": 0.80}


def load_data(path: Path) -> pd.DataFrame:
    """Lee el dataset desde un CSV."""
    return pd.read_csv(path)


def split_data(data: pd.DataFrame, test_size: float = 0.2, random_state: int = 42):
    """Divide en train/test estratificado."""
    X = data[FEATURES]
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
    """Entrena un RandomForestClassifier.

    Los valores por defecto son los ganadores de `ml/pipeline/tune.py`
    (CV 5-fold, mejor F1 macro que cumple los umbrales por clase).
    `class_weight="balanced_subsample"` compensa el desbalance (Enrolled es
    ~18 % del total) y duplica su recall a cambio de algo de accuracy.
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


def evaluate_detailed(model, X_test, y_test) -> dict:
    """Métricas completas: accuracy, F1 macro, métricas por clase y matriz de confusión."""
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
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro")),
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
    """Importancia (Gini) de cada feature, ordenada de mayor a menor."""
    pairs = sorted(zip(FEATURES, model.feature_importances_), key=lambda p: p[1], reverse=True)
    pairs = [(name, float(value)) for name, value in pairs]
    return pairs[:top] if top else pairs


def reference_profile(X: pd.DataFrame, bins: int = 10) -> dict:
    """Perfil de referencia de cada feature para detectar data drift.

    Guarda los bordes de los cuantiles y la proporción de datos en cada
    bin; `ml/monitoring/drift.py` compara contra este perfil (PSI + KS).
    """
    profile = {}
    for col in FEATURES:
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
