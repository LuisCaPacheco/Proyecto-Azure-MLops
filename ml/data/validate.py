"""Validación del dataset ENAPE antes de entrenar.

Dos niveles:

1. **Estructural** (errores): columnas esperadas, tipos numéricos, mínimo de
   filas, clases conocidas y con representación suficiente. Si falla, el
   stage ``DataPrep`` del pipeline se detiene: no tiene sentido depurar ni
   entrenar con un archivo que no es el dataset.
2. **Por fila** (``ROW_RULES``): nulos, valores fuera de rango/dominio y
   duplicados. Son las mismas reglas del Mapping Data Flow de Azure Data
   Factory (``terraform/dataflows/clean_enape.dfs``), que es quien descarta
   esas filas en la nube. Aquí solo se cuentan, y se falla si superan
   ``--max-rejected-ratio`` (fuente dañada). ``clean()`` aplica las reglas en
   local, como equivalente del Data Flow para el pipeline sin Azure.

Uso:
    python -m ml.data.validate --data ml/data/enape.csv --report validation.json
    python -m ml.data.validate --data sucio.csv --clean-output limpio.csv
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from ml.data.load_enape import CLASSES, FEATURES, LABEL, TARGET

MIN_ROWS = 1000
# Abandona es ~6,5 % del dataset: el mínimo global no puede ser 5 %.
MIN_CLASS_SHARE = 0.03

# columna -> (mínimo, máximo) permitidos; mantener en sincronía con clean_enape.dfs
RANGE_RULES = {
    "edad": (6, 100),
    "q_personas": (1, 30),
    "q_hombres": (0, 30),
    "q_mujeres": (0, 30),
    "menores_30": (0, 30),
}
# columnas categóricas codificadas -> dominio permitido
CATEGORICAL_DOMAINS = {
    "edu_inicial": {0, 1, 2},
    "nivel_edu": set(range(0, 13)),
    "ent": set(range(1, 33)),
    "max_nivel_esp": set(range(0, 10)),
    "entr_diagnost": {0, 1, 2, 9},
}
# Binarias 1=sí / 0=no (ya recodificadas por load_enape.py)
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


def invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Una columna booleana por regla: True donde la fila la incumple."""
    issues = pd.DataFrame(index=df.index)
    issues["target_invalido"] = ~pd.to_numeric(df[TARGET], errors="coerce").isin(
        range(len(CLASSES))
    )
    issues["target_label_invalido"] = ~df[LABEL].isin(CLASSES)
    expected_label = pd.to_numeric(df[TARGET], errors="coerce").map(
        {i: name for i, name in enumerate(CLASSES)}
    )
    issues["target_label_inconsistente"] = df[LABEL] != expected_label
    for column, (low, high) in RANGE_RULES.items():
        values = pd.to_numeric(df[column], errors="coerce")
        issues[f"{column}_fuera_de_rango"] = values.isna() | (values < low) | (values > high)
    for column, domain in CATEGORICAL_DOMAINS.items():
        values = pd.to_numeric(df[column], errors="coerce")
        issues[f"{column}_fuera_de_dominio"] = ~values.isin(domain)
    for column in BINARY_COLUMNS:
        issues[f"{column}_no_binario"] = ~pd.to_numeric(
            df[column], errors="coerce"
        ).isin([0, 1])
    return issues


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Equivalente local del Data Flow de ADF: devuelve (válidas sin duplicados, rechazadas)."""
    bad = invalid_rows(df).any(axis=1)
    return df[~bad].drop_duplicates(), df[bad]


def validate(df: pd.DataFrame, max_rejected_ratio: float = 0.05) -> dict:
    """Devuelve el reporte de validación; ``ok`` es False si hay errores."""
    errors = []
    required = ["FOLIO", *FEATURES, TARGET, LABEL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        # sin el esquema no se pueden evaluar las demás reglas
        return {"ok": False, "rows": len(df), "errors": [f"Faltan columnas: {missing}"]}

    if len(df) < MIN_ROWS:
        errors.append(f"Solo {len(df)} filas (mínimo {MIN_ROWS})")

    non_numeric = [c for c in FEATURES if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        errors.append(f"Columnas no numéricas: {non_numeric}")

    shares = df[LABEL].value_counts(normalize=True)
    for name in CLASSES:
        share = float(shares.get(name, 0.0))
        if share < MIN_CLASS_SHARE:
            errors.append(
                f"Clase {name}: {share:.1%} de las filas (mínimo {MIN_CLASS_SHARE:.0%})"
            )

    issues = invalid_rows(df)
    bad = issues.any(axis=1)
    duplicates = int(df[~bad].duplicated().sum())
    rejected_ratio = (int(bad.sum()) + duplicates) / max(len(df), 1)
    if rejected_ratio > max_rejected_ratio:
        errors.append(
            f"{rejected_ratio:.1%} de las filas serían descartadas (máximo {max_rejected_ratio:.0%})"
        )

    return {
        "ok": not errors,
        "rows": len(df),
        "errors": errors,
        "null_cells": int(df[required].isna().sum().sum()),
        "invalid_rows": int(bad.sum()),
        "duplicate_rows": duplicates,
        "rejected_ratio": round(rejected_ratio, 4),
        "row_issues": {rule: int(n) for rule, n in issues.sum().items() if n},
        "class_distribution": {
            name: round(float(shares.get(name, 0.0)), 4) for name in CLASSES
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida el dataset ENAPE 2021")
    parser.add_argument("--data", type=Path, default=Path(__file__).parent / "enape.csv")
    parser.add_argument("--max-rejected-ratio", type=float, default=0.05)
    parser.add_argument("--expected-rows", type=int, default=None, help="Falla si el tamaño de cohorte difiere")
    parser.add_argument("--report", type=Path, default=None, help="JSON con el reporte")
    parser.add_argument(
        "--clean-output",
        type=Path,
        default=None,
        help="Guarda el CSV depurado (equivalente local del Data Flow de ADF)",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    report = validate(df, args.max_rejected_ratio)
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if not report["ok"]:
        print("Validación FALLIDA", file=sys.stderr)
        sys.exit(1)
    if args.expected_rows is not None and report["rows"] != args.expected_rows:
        print(
            f"Validación FALLIDA: se esperaban {args.expected_rows} filas y hay {report['rows']}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.clean_output:
        valid, rejected = clean(df)
        args.clean_output.parent.mkdir(parents=True, exist_ok=True)
        valid.to_csv(args.clean_output, index=False)
        print(f"{len(valid)} filas válidas -> {args.clean_output} ({len(rejected)} rechazadas)")


if __name__ == "__main__":
    main()
