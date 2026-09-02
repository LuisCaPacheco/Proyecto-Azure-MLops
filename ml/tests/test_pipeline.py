"""Tests unitarios del pipeline de entrenamiento/evaluación.

Usan la lógica pura de `modeling.py` (sin MLflow) para ser ejecutables
sin servidor de tracking.
"""

import pandas as pd

from ml.pipeline.modeling import FEATURES, TARGET, load_data, split_data, train_model, evaluate_model


def test_load_data_reads_csv(tmp_path) -> None:
    csv_path = tmp_path / "iris.csv"
    pd.DataFrame(
        {
            **{f: [0.0, 1.0] for f in FEATURES},
            TARGET: [0, 1],
        }
    ).to_csv(csv_path, index=False)

    df = load_data(csv_path)
    assert len(df) == 2
    assert TARGET in df.columns


def test_split_data_stratified() -> None:
    data = pd.DataFrame(
        {
            **{f: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0] for f in FEATURES},
            TARGET: [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2],
        }
    )
    X_tr, X_te, y_tr, y_te = split_data(data, test_size=0.5, random_state=1)
    assert len(X_tr) == 6
    assert len(X_te) == 6
    # todas las clases siguen presentes en train y test
    assert set(y_tr.unique()) == {0, 1, 2}
    assert set(y_te.unique()) == {0, 1, 2}


def test_train_and_evaluate() -> None:
    data = _iris_sample()
    X_tr, X_te, y_tr, y_te = split_data(data, test_size=0.25, random_state=0)
    model = train_model(X_tr, y_tr, n_estimators=20, max_depth=3)
    acc = evaluate_model(model, X_te, y_te)
    assert 0.0 <= acc <= 1.0


def _iris_sample() -> pd.DataFrame:
    """Dataset sintético de iris con 90 filas (30 por clase)."""
    import numpy as np

    rng = np.random.RandomState(42)
    rows = []
    for cls, centers in enumerate(
        [
            [5.0, 3.4, 1.5, 0.2],
            [6.0, 2.9, 4.2, 1.3],
            [6.6, 3.0, 5.6, 2.1],
        ]
    ):
        for _ in range(30):
            row = [c + rng.normal(0, 0.4) for c in centers]
            rows.append(row + [cls])
    return pd.DataFrame(rows, columns=FEATURES + [TARGET]).round(2)
