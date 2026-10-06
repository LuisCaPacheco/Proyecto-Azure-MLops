"""Carga y preparación del dataset de deserción universitaria (UCI).

Dataset: *Predict Students' Dropout and Academic Success* (UCI ML Repository,
id 697): 4424 estudiantes, 36 características académicas, demográficas y
socioeconómicas, y una variable objetivo con tres clases:
``Dropout`` (abandona), ``Enrolled`` (sigue matriculado) y ``Graduate``.

Este script es la etapa de *data-prep* del pipeline:

1. Descarga el ZIP oficial de UCI (o usa un CSV crudo local con ``--raw``).
2. Normaliza los nombres de columna a ``snake_case`` (el CSV original usa
   ``;`` como separador y trae nombres con espacios, tabs y paréntesis).
3. Codifica la clase objetivo (``target`` 0/1/2 + ``target_label``).
4. Guarda ``ml/data/dropout.csv``, que luego se sube al contenedor ``raw``
   de Azure Blob Storage y es el input del job de entrenamiento.
"""

import argparse
import io
import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

UCI_URL = (
    "https://archive.ics.uci.edu/static/public/697/"
    "predict+students+dropout+and+academic+success.zip"
)

# Orden fijo de clases: el índice es el valor de `target`
CLASSES = ["Dropout", "Enrolled", "Graduate"]

# Corrección de errores tipográficos de la fuente original
RENAMES = {"nacionality": "nationality"}


def to_snake(name: str) -> str:
    """Convierte un nombre de columna del CSV original a snake_case."""
    name = name.strip().lower().replace("'", "")
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return RENAMES.get(name, name)


def download_raw(url: str = UCI_URL) -> pd.DataFrame:
    """Descarga el ZIP de UCI y devuelve el CSV crudo como DataFrame."""
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        with zf.open("data.csv") as fh:
            return pd.read_csv(fh, sep=";")


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas y codifica la clase objetivo."""
    df = raw.copy()
    df.columns = [to_snake(c) for c in df.columns]
    df = df.rename(columns={"target": "target_label"})
    df["target_label"] = df["target_label"].str.strip()

    unknown = set(df["target_label"]) - set(CLASSES)
    if unknown:
        raise ValueError(f"Clases inesperadas en el dataset: {unknown}")

    df["target"] = df["target_label"].map({c: i for i, c in enumerate(CLASSES)})
    return df


def load_dropout_dataframe(raw_path: Path | None = None) -> pd.DataFrame:
    """Devuelve el dataset preparado, desde un CSV crudo local o desde UCI."""
    raw = pd.read_csv(raw_path, sep=";") if raw_path is not None else download_raw()
    return prepare(raw)


def save_dropout_csv(path: Path = DATA_DIR / "dropout.csv", raw_path: Path | None = None) -> None:
    """Guarda el dataset preparado como CSV local."""
    df = load_dropout_dataframe(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Dataset guardado en {path} ({len(df)} filas, {len(df.columns)} columnas)")
    print(f"Distribución de clases: {df['target_label'].value_counts().to_dict()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el CSV del dataset de deserción (UCI 697)")
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "dropout.csv",
        help="Ruta de salida del CSV (por defecto ml/data/dropout.csv)",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=None,
        help="CSV crudo de UCI (separador ';'); si se omite se descarga de UCI",
    )
    args = parser.parse_args()
    save_dropout_csv(args.output, args.raw)
