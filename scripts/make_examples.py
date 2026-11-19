"""Genera los JSON de ejemplo de endpoint/examples/ a partir del dataset ENAPE."""

import json
from pathlib import Path

from ml.data.load_enape import FEATURES, TARGET
from ml.pipeline.modeling import load_data

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ml" / "data" / "enape.csv"
OUT = ROOT / "endpoint" / "examples"


def as_student(row) -> dict:
    """Convierte una fila del CSV en el diccionario que acepta el endpoint."""
    return {feature: int(row[feature]) for feature in FEATURES}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_data(DATA)

    # Estudiante que realmente abandonó y sin recursos digitales en el hogar
    risky = df[(df[TARGET] == 1) & (df["internet_f"] == 0) & (df["laptop"] == 0)]
    # Estudiante que continuó, con internet fijo y computadora
    safe = df[(df[TARGET] == 0) & (df["internet_f"] == 1) & (df["laptop"] == 1)]

    (OUT / "estudiante_riesgo_alto.json").write_text(
        json.dumps({"student": as_student(risky.iloc[0])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "estudiante_riesgo_bajo.json").write_text(
        json.dumps({"student": as_student(safe.iloc[0])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "lote_5_estudiantes.json").write_text(
        json.dumps(
            {"students": [as_student(row) for _, row in df.head(5).iterrows()]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Ejemplos escritos en {OUT}")


if __name__ == "__main__":
    main()
