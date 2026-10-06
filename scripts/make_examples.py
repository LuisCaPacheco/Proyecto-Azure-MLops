"""Genera los JSON de ejemplo de endpoint/examples/ a partir del set de test."""

import json
from pathlib import Path

from ml.pipeline.modeling import load_data, split_data

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "endpoint" / "examples"


def as_student(row) -> dict:
    return {k: float(v) for k, v in row.items()}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _, X_test, _, y_test = split_data(load_data(ROOT / "ml" / "data" / "dropout.csv"))

    # Estudiante que realmente desertó: pocas materias aprobadas y con deuda
    risky = X_test[(y_test == 0) & (X_test["curricular_units_1st_sem_approved"] <= 2) & (X_test["debtor"] == 1)]
    graduate = X_test[y_test == 2]

    (OUT / "estudiante_riesgo_alto.json").write_text(
        json.dumps({"student": as_student(risky.iloc[0])}, indent=2))
    (OUT / "estudiante_riesgo_bajo.json").write_text(
        json.dumps({"student": as_student(graduate.iloc[0])}, indent=2))
    (OUT / "lote_5_estudiantes.json").write_text(
        json.dumps({"students": [as_student(r) for _, r in X_test.head(5).iterrows()]}, indent=2))
    print(f"Ejemplos escritos en {OUT}")


if __name__ == "__main__":
    main()
