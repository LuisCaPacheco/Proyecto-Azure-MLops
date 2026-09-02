"""Lógica pura de entrenamiento/evaluación (sin dependencia de MLflow).

Separada de `train.py` para que pueda probarse unitariamente sin
necesidad de un servidor de tracking de MLflow.
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

FEATURES = ["sepal length (cm)", "sepal width (cm)", "petal length (cm)", "petal width (cm)"]
TARGET = "target"


def load_data(path: Path) -> pd.DataFrame:
    """Lee el dataset desde un CSV."""
    return pd.read_csv(path)


def split_data(data: pd.DataFrame, test_size: float = 0.25, random_state: int = 42):
    """Divide en train/test estratificado."""
    X = data[FEATURES]
    y = data[TARGET]
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)


def train_model(X_train, y_train, n_estimators: int = 100, max_depth: int = 4):
    """Entrena un RandomForestClassifier."""
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=42,
    ).fit(X_train, y_train)


def evaluate_model(model, X_test, y_test) -> float:
    """Evalúa en test y devuelve accuracy."""
    y_pred = model.predict(X_test)
    return float(accuracy_score(y_test, y_pred))


def save_model(model, path: Path) -> None:
    """Guarda el modelo con joblib."""
    path.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path / "model.pkl")
