"""Tests unitarios del módulo ml/data (preparación del dataset de deserción)."""

from pathlib import Path

import pandas as pd
import pytest

from ml.data.load_data import CLASSES, prepare, to_snake
from ml.pipeline.modeling import FEATURES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_to_snake_normalizes_original_names() -> None:
    assert to_snake("Daytime/evening attendance\t") == "daytime_evening_attendance"
    assert to_snake("Mother's qualification") == "mothers_qualification"
    assert to_snake("Curricular units 1st sem (approved)") == "curricular_units_1st_sem_approved"
    assert to_snake("Nacionality") == "nationality"


def test_prepare_encodes_target() -> None:
    raw = pd.DataFrame({"Age at enrollment": [18, 25, 30], "Target": ["Dropout", "Graduate ", "Enrolled"]})
    df = prepare(raw)
    assert list(df["target"]) == [0, 2, 1]
    assert list(df["target_label"]) == ["Dropout", "Graduate", "Enrolled"]
    assert "age_at_enrollment" in df.columns


def test_prepare_rejects_unknown_classes() -> None:
    raw = pd.DataFrame({"Target": ["Dropout", "Transferido"]})
    with pytest.raises(ValueError):
        prepare(raw)


def test_dropout_csv_matches_schema() -> None:
    path = DATA_DIR / "dropout.csv"
    assert path.exists(), "Genera el CSV con: python -m ml.data.load_data"
    df = pd.read_csv(path)
    assert len(df) == 4424
    assert set(FEATURES) <= set(df.columns)
    assert set(df["target_label"]) == set(CLASSES)
