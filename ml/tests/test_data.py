"""Tests unitarios del módulo ml/data."""

from pathlib import Path

import pandas as pd

from ml.data.load_data import load_iris_dataframe

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_load_iris_shape() -> None:
    df = load_iris_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 150
    assert df.shape[1] >= 5


def test_load_iris_target_values() -> None:
    df = load_iris_dataframe()
    assert set(df["target"].unique()) == {0, 1, 2}


def test_iris_csv_exists() -> None:
    assert (DATA_DIR / "iris.csv").exists(), "Genera el CSV con: python ml/data/load_data.py"
