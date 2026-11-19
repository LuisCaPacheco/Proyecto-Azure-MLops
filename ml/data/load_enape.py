"""Carga y preparación del dataset ENAPE 2021 (INEGI, México).

Fuente: *Encuesta Nacional de Acceso y Permanencia en la Educación* (ENAPE)
2021. El archivo ``archive (1)/df03_Dataset_ENAPE.csv`` (32.343 x 67) es el
join de ``df01_TipoVivienda`` + ``df02_TipoModulo`` por ``FOLIO``, con los
duplicados de ``ENT``/``FACTOR_y`` ya eliminados.

Este script es la etapa de *data-prep* del pipeline:

1. Lee el CSV crudo.
2. Aplica la cohorte de estudio:
   ``inscrito == 1`` (estuvo inscrito en 2020-2021),
   ``EDAD >= 6``,
   ``inscrito_actual in {1, 2}`` (se conoce si sigue inscrito en 2021-2022) y
   ``inscrito_actual == 2`` y ``nins_causa == 4`` (egreso; se excluye esta combinación
   por meta cumplida; no se clasifica como abandono).
   Resultado esperado: **18.207 filas**.
3. Deriva la etiqueta binaria ``abandono``:
   ``abandono = 1`` si ``inscrito_actual == 2`` (no se reinscribió en
   2021-2022 por una causa distinta de haber cumplido su meta), ``0`` si
   ``inscrito_actual == 1`` (continúa). Dentro de la cohorte esta regla es
   equivalente a ``nins_causa != 0``; el porcentaje de positivos es ~6,48 %
   (1.179 casos).
4. Renombra las columnas al contrato snake_case, recodifica los binarios
   codificados como 1=sí / 2=no a 1/0 y deja ``abandono_label``
   (``"Continua"``/``"Abandona"``).
5. Guarda ``ml/data/enape.csv`` con las 18 features del contrato, la etiqueta
   y ``FOLIO``.

Nota de fuga estructural: ``max_nivel_esp`` y ``entr_diagnost`` se conservan
en el CSV (forman parte del contrato de 18 features) pero **no se usan para
entrenar** (ver ``MODEL_FEATURES`` en ``ml/pipeline/modeling.py``). En ENAPE
ambas preguntas solo se aplican a quien está inscrito en el ciclo actual, así
que el código 0 identifica casi perfectamente a quien abandonó (ROC-AUC
espuria ~1.0). El pipeline los excluye del modelo igual que las variables
``m_*``, ``med_*``, ``t_*`` o de bienestar socioemocional.

Uso:
    python -m ml.data.load_enape --output ml/data/enape.csv
    python -m ml.data.load_enape --raw ruta/df03_Dataset_ENAPE.csv
"""

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent
RAW_DEFAULT = REPO_ROOT / "archive (1)" / "df03_Dataset_ENAPE.csv"

# Orden fijo de clases: el índice es el valor de `abandono`
CLASSES = ["Continua", "Abandona"]
TARGET = "abandono"
LABEL = "abandono_label"

# Contrato de 18 features (orden fijo: es el orden que espera el endpoint).
# Todas se observan antes de cursar el ciclo 2021-2022.
FEATURES = [
    "sexo",
    "edad",
    "edu_inicial",
    "nivel_edu",
    "terminado",
    "ent",
    "q_personas",
    "q_hombres",
    "q_mujeres",
    "menores_30",
    "pc",
    "laptop",
    "tv_plana",
    "tablet",
    "smartphone",
    "internet_f",
    "max_nivel_esp",
    "entr_diagnost",
]

# Columnas que, aunque están en el contrato, se excluyen del modelo por fuga
# estructural (solo se preguntan a quien sigue inscrito; el código 0 delata
# la etiqueta). Mantener en sincronía con `ml/pipeline/modeling.py`.
LEAKY_FEATURES = ("max_nivel_esp", "entr_diagnost")

RENAMES = {
    "SEXO": "sexo",
    "ENT": "ent",
    "InternetF": "internet_f",
    "x<30": "menores_30",
    "EDAD": "edad",
}

# En ENAPE los binarios vienen como 1=sí / 2=no; el contrato usa 0/1.
BINARY_COLUMNS = [
    "sexo",
    "terminado",
    "pc",
    "laptop",
    "tv_plana",
    "tablet",
    "smartphone",
    "internet_f",
]

RAW_COHORT_COLUMNS = [
    "FOLIO",
    "SEXO",
    "EDAD",
    "edu_inicial",
    "inscrito",
    "nivel_edu",
    "terminado",
    "inscrito_actual",
    "nins_causa",
    "entr_diagnost",
    "q_personas",
    "q_hombres",
    "q_mujeres",
    "x<30",
    "pc",
    "laptop",
    "tv_plana",
    "tablet",
    "smartphone",
    "InternetF",
    "max_nivel_esp",
    "ENT",
]

# La cohorte de referencia del CSV fuente ENAPE 2021 usado en este proyecto.
EXPECTED_ROWS = 18_207


def cohort_mask(raw: pd.DataFrame) -> pd.Series:
    """Filas que forman la cohorte de abandono (18.207 en ENAPE 2021)."""
    return (
        (raw["inscrito"] == 1)
        & (raw["EDAD"] >= 6)
        & raw["inscrito_actual"].isin([1, 2])
        & ~((raw["inscrito_actual"] == 2) & (raw["nins_causa"] == 4))
    )


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Aplica cohorte, deriva la etiqueta y normaliza el esquema."""
    missing = [c for c in RAW_COHORT_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas del CSV crudo de ENAPE: {missing}")

    df = raw.loc[cohort_mask(raw)].copy()

    # Regla de etiqueta: no reinscrito en 2021-2022 por causa distinta de
    # "cumplió su meta educativa" (nins_causa == 4 ya quedó fuera).
    df[TARGET] = (df["inscrito_actual"] == 2).astype(int)
    df = df.rename(columns=RENAMES)

    for column in BINARY_COLUMNS:
        df[column] = df[column].replace({2: 0})

    # El contrato es numérico entero (el endpoint y los Data Flows usan int).
    for column in FEATURES:
        df[column] = pd.to_numeric(df[column], errors="raise").astype(int)
    df["FOLIO"] = df["FOLIO"].astype(int)

    unknown = set(df[TARGET].unique()) - set(range(len(CLASSES)))
    if unknown:
        raise ValueError(f"Valores inesperados en {TARGET}: {unknown}")
    df[LABEL] = [CLASSES[value] for value in df[TARGET]]

    if len(df) != EXPECTED_ROWS:
        raise ValueError(
            f"La cohorte ENAPE esperada tiene {EXPECTED_ROWS:,} filas; se generaron {len(df):,}. "
            "Verifica que se usó el CSV fuente correcto."
        )

    return df[["FOLIO", *FEATURES, TARGET, LABEL]]


def load_enape_dataframe(raw_path: Path | None = None) -> pd.DataFrame:
    """Lee el CSV crudo de ENAPE y devuelve el dataset preparado."""
    path = RAW_DEFAULT if raw_path is None else Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el CSV crudo de ENAPE en {path}. "
            "Pasa --raw con la ruta de df03_Dataset_ENAPE.csv."
        )
    return prepare(pd.read_csv(path))


def save_enape_csv(path: Path = DATA_DIR / "enape.csv", raw_path: Path | None = None) -> pd.DataFrame:
    """Guarda el dataset preparado como CSV local y devuelve el DataFrame."""
    df = load_enape_dataframe(raw_path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    positive = float(df[TARGET].mean()) if len(df) else 0.0
    print(f"Dataset guardado en {path} ({len(df)} filas, {len(df.columns)} columnas)")
    print(f"Distribución de clases: {df[LABEL].value_counts().to_dict()}")
    print(f"Positivos (Abandona): {int(df[TARGET].sum())} ({positive:.2%})")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el CSV del dataset ENAPE 2021")
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "enape.csv",
        help="Ruta de salida del CSV (por defecto ml/data/enape.csv)",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=None,
        help="CSV crudo de ENAPE; por defecto archive (1)/df03_Dataset_ENAPE.csv",
    )
    args = parser.parse_args()
    save_enape_csv(args.output, args.raw)
