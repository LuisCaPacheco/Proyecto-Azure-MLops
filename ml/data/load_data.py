"""Carga y descarga local del dataset Iris.

Este script genera el CSV local `ml/data/iris.csv` a partir de
`sklearn.datasets.load_iris`. También sirve como base del "data-prep"
para subir los datos a Azure Blob Storage (contenedor `raw`).
"""

import argparse
from pathlib import Path

import pandas as pd
from sklearn.datasets import load_iris

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_iris_dataframe() -> pd.DataFrame:
    """Carga Iris desde scikit-learn y devuelve un DataFrame tabular."""
    data = load_iris(as_frame=True)
    df = data.frame
    df.columns = list(data.feature_names) + ["target"]
    df["species"] = df["target"].map(
        {i: name for i, name in enumerate(data.target_names)}
    )
    return df


def save_iris_csv(path: Path = DATA_DIR / "iris.csv") -> None:
    """Guarda el dataset Iris como CSV local."""
    df = load_iris_dataframe()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Dataset guardado en {path} ({len(df)} filas, {len(df.columns)} columnas)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el CSV del dataset Iris")
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "iris.csv",
        help="Ruta de salida del CSV (por defecto ml/data/iris.csv)",
    )
    args = parser.parse_args()
    save_iris_csv(args.output)
