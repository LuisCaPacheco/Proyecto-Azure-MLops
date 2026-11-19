"""Tests unitarios de la preparación del dataset ENAPE 2021."""

from pathlib import Path

import pandas as pd
import pytest

from ml.data.load_enape import CLASSES, FEATURES, LABEL, TARGET, cohort_mask, prepare
from ml.pipeline.modeling import MODEL_FEATURES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _raw() -> pd.DataFrame:
    """CSV crudo mínimo con las columnas que usa el loader."""
    return pd.DataFrame(
        {
            "FOLIO": [1, 2, 3, 4],
            "SEXO": [1, 2, 1, 2],
            "EDAD": [10, 20, 30, 40],
            "edu_inicial": [1, 1, 2, 1],
            "inscrito": [1, 1, 1, 1],
            "nivel_edu": [1, 6, 9, 3],
            "terminado": [1, 1, 2, 1],
            "inscrito_actual": [1, 2, 1, 2],
            "nins_causa": [0, 1, 0, 4],
            "entr_diagnost": [1, 9, 2, 1],
            "q_personas": [3, 4, 5, 6],
            "q_hombres": [1, 2, 2, 3],
            "q_mujeres": [2, 2, 3, 3],
            "x<30": [2, 1, 2, 1],
            "pc": [1, 2, 1, 2],
            "laptop": [1, 1, 2, 2],
            "tv_plana": [2, 1, 1, 2],
            "tablet": [2, 2, 1, 1],
            "smartphone": [1, 1, 1, 2],
            "InternetF": [1, 2, 1, 1],
            "max_nivel_esp": [1, 9, 2, 1],
            "ENT": [1, 2, 3, 4],
        }
    )


def test_cohort_mask_excludes_meta_graduates() -> None:
    raw = _raw()
    # nins_causa == 4 (cumplió su meta) no es abandono: queda fuera
    assert cohort_mask(raw).tolist() == [True, True, True, False]


def test_prepare_builds_contract_and_label() -> None:
    df = prepare(_raw())
    assert list(df.columns) == ["FOLIO", *FEATURES, TARGET, LABEL]
    assert len(df) == 3
    assert list(df[TARGET]) == [0, 1, 0]
    assert list(df[LABEL]) == ["Continua", "Abandona", "Continua"]


def test_prepare_recodes_binaries_to_zero_one() -> None:
    df = prepare(_raw())
    # SEXO venía como 1/2 y pasa a 1/0, igual que los sí/no del hogar
    assert list(df["sexo"]) == [1, 0, 1]
    assert list(df["internet_f"]) == [1, 0, 1]
    for column in ("sexo", "terminado", "pc", "laptop", "tv_plana", "tablet", "smartphone", "internet_f"):
        assert set(df[column]) <= {0, 1}


def test_model_features_exclude_structural_leaks() -> None:
    assert "max_nivel_esp" not in MODEL_FEATURES
    assert "entr_diagnost" not in MODEL_FEATURES
    assert len(MODEL_FEATURES) == len(FEATURES) - 2


def test_prepare_rejects_missing_columns() -> None:
    raw = _raw().drop(columns=["inscrito_actual"])
    with pytest.raises(ValueError, match="Faltan columnas"):
        prepare(raw)


def test_enape_csv_matches_schema(tmp_path) -> None:
    path = DATA_DIR / "enape.csv"
    if not path.exists():
        from ml.data.load_enape import load_enape_dataframe

        raw = DATA_DIR.parent.parent / "archive (1)" / "df03_Dataset_ENAPE.csv"
        assert raw.exists(), "No se encuentra la fuente cruda archive (1)/df03_Dataset_ENAPE.csv"
        load_enape_dataframe(raw).to_csv(tmp_path / "enape.csv", index=False)
        path = tmp_path / "enape.csv"
    df = pd.read_csv(path)
    assert len(df) == 18_207
    assert set(FEATURES) <= set(df.columns)
    assert set(df[LABEL]) == set(CLASSES)
    assert 0.05 < df[TARGET].mean() < 0.08
