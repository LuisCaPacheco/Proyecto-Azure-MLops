"""Tests de la validación del dataset ENAPE (ml/data/validate.py)."""

from pathlib import Path

import pandas as pd
import pytest

from ml.data.validate import clean, validate

DATA = Path(__file__).resolve().parent.parent / "data" / "enape.csv"


@pytest.fixture(scope="module")
def dataset() -> pd.DataFrame:
    if DATA.exists():
        return pd.read_csv(DATA)
    from ml.data.load_enape import load_enape_dataframe

    raw = DATA.parents[2] / "archive (1)" / "df03_Dataset_ENAPE.csv"
    if not raw.exists():
        pytest.fail("No se encuentra ml/data/enape.csv ni su fuente archive (1)/df03_Dataset_ENAPE.csv")
    return load_enape_dataframe(raw)


def test_real_dataset_is_valid(dataset) -> None:
    report = validate(dataset)
    assert report["ok"], report["errors"]
    assert report["rows"] == 18_207


def test_cli_expected_rows_rejects_incorrect_cohort(tmp_path) -> None:
    import subprocess
    import sys

    path = tmp_path / "small.csv"
    dataset = pd.DataFrame(
        {
            "FOLIO": range(1000),
            "sexo": [0, 1] * 500,
            "edad": [20] * 1000,
            "edu_inicial": [1] * 1000,
            "nivel_edu": [6] * 1000,
            "terminado": [0, 1] * 500,
            "ent": [1] * 1000,
            "q_personas": [3] * 1000,
            "q_hombres": [1] * 1000,
            "q_mujeres": [2] * 1000,
            "menores_30": [1] * 1000,
            "pc": [0, 1] * 500,
            "laptop": [0, 1] * 500,
            "tv_plana": [0, 1] * 500,
            "tablet": [0, 1] * 500,
            "smartphone": [0, 1] * 500,
            "internet_f": [0, 1] * 500,
            "max_nivel_esp": [1] * 1000,
            "entr_diagnost": [1] * 1000,
            "abandono": [0, 1] * 500,
            "abandono_label": ["Continua", "Abandona"] * 500,
        }
    )
    dataset.to_csv(path, index=False)
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "ml.data.validate", "--data", str(path), "--expected-rows", "18207"],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    assert result.returncode == 1
    assert "se esperaban 18207 filas" in result.stderr
    assert report["invalid_rows"] == 0 and report["null_cells"] == 0
    assert report["class_distribution"]["Abandona"] == pytest.approx(0.0648, abs=1e-3)


def test_missing_column_is_an_error(dataset) -> None:
    report = validate(dataset.drop(columns=["edad"]))
    assert not report["ok"]
    assert "edad" in report["errors"][0]


def test_too_few_rows_is_an_error(dataset) -> None:
    report = validate(dataset.head(50))
    assert not report["ok"]
    assert any("filas" in e for e in report["errors"])


def test_missing_class_is_an_error(dataset) -> None:
    report = validate(dataset[dataset["abandono_label"] != "Abandona"])
    assert not report["ok"]
    assert any("Abandona" in e for e in report["errors"])


def test_few_dirty_rows_are_counted_not_fatal(dataset) -> None:
    dirty = dataset.drop_duplicates().copy()
    dirty.loc[0, "edad"] = 250                 # fuera de rango
    dirty.loc[1, "nivel_edu"] = 99             # fuera de dominio
    dirty.loc[2, "laptop"] = 7                 # no binario
    dirty = pd.concat([dirty, dirty.iloc[[10]]])  # duplicado
    report = validate(dirty)
    assert report["ok"]
    assert report["invalid_rows"] == 3 and report["duplicate_rows"] == 1
    assert report["row_issues"]["edad_fuera_de_rango"] == 1
    assert report["row_issues"]["laptop_no_binario"] == 1


def test_many_dirty_rows_fail(dataset) -> None:
    dirty = dataset.copy()
    dirty.loc[dirty.index[:1500], "edad"] = -1
    report = validate(dirty)
    assert not report["ok"]
    assert any("descartadas" in e for e in report["errors"])


def test_clean_drops_invalid_and_duplicates(dataset) -> None:
    dirty = dataset.drop_duplicates().copy()
    dirty.loc[0, "q_personas"] = 99
    dirty.loc[1, "abandono"] = 5
    dirty = pd.concat([dirty, dirty.iloc[[10]]])
    valid, rejected = clean(dirty)
    assert len(rejected) == 2
    assert len(valid) == len(dirty) - 3  # 2 inválidas + 1 duplicada
    assert validate(valid)["invalid_rows"] == 0
