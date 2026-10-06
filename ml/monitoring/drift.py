"""Detección de data drift en el perfil de los estudiantes que llegan al endpoint.

Compara un lote "actual" (inferencias registradas por el endpoint, o un CSV
con nuevos estudiantes) contra el perfil de referencia del entrenamiento
(`reference_profile.json`, artefacto `evaluation/` del run en MLflow):

- PSI (Population Stability Index) por variable, sobre los bins de cuantiles
  del entrenamiento. Regla usual: < 0.10 estable, 0.10-0.25 moderado,
  > 0.25 drift significativo.
- Prueba KS de dos muestras (scipy) como segunda señal para variables continuas.

El pipeline programado (`.azure-pipelines/drift-monitoring.yml`) lo ejecuta a
diario; si hay drift significativo sale con código 1 y dispara el reentrenamiento.

Uso:
    # lote desde CSV
    python -m ml.monitoring.drift --reference outputs/reference_profile.json --current nuevos.csv
    # lote desde los logs JSON del endpoint (una línea por inferencia)
    python -m ml.monitoring.drift --reference ... --current-logs inference.log
    # simulación de un choque económico (demo)
    python -m ml.monitoring.drift --reference ... --simulate-from ml/data/dropout.csv
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

PSI_MODERATE = 0.10
PSI_SIGNIFICANT = 0.25
EPS = 1e-4


def psi(expected: np.ndarray, actual: np.ndarray) -> float:
    """Population Stability Index entre dos distribuciones por bins."""
    expected = np.clip(np.asarray(expected, dtype=float), EPS, None)
    actual = np.clip(np.asarray(actual, dtype=float), EPS, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def bin_proportions(values: np.ndarray, edges: list[float]) -> np.ndarray:
    """Proporción de `values` en los bins de referencia (los extremos quedan abiertos)."""
    inner = np.asarray(edges[1:-1], dtype=float)
    idx = np.searchsorted(inner, values, side="right")
    counts = np.bincount(idx, minlength=len(edges) - 1)
    return counts / max(len(values), 1)


def drift_report(profile: dict, current: pd.DataFrame) -> dict:
    """Calcula PSI y KS por variable y un veredicto global."""
    features = {}
    for col, ref in profile.items():
        if col not in current:
            continue
        values = current[col].to_numpy(dtype=float)
        score = psi(ref["proportions"], bin_proportions(values, ref["edges"]))
        ks = ks_2samp(ref["sample"], values)
        status = "estable"
        if score > PSI_SIGNIFICANT:
            status = "drift"
        elif score > PSI_MODERATE:
            status = "moderado"
        features[col] = {
            "psi": round(score, 4),
            "ks_statistic": round(float(ks.statistic), 4),
            "ks_pvalue": float(ks.pvalue),
            "ref_mean": round(ref["mean"], 4),
            "cur_mean": round(float(values.mean()), 4),
            "status": status,
        }

    drifted = sorted((c for c, f in features.items() if f["status"] == "drift"),
                     key=lambda c: -features[c]["psi"])
    moderate = [c for c, f in features.items() if f["status"] == "moderado"]
    return {
        "n_current": int(len(current)),
        "n_features": len(features),
        "drifted_features": drifted,
        "moderate_features": moderate,
        "share_drifted": round(len(drifted) / max(len(features), 1), 4),
        # Reentrenar si deriva >= 10 % de las variables o alguna variable académica clave
        "retrain_recommended": bool(
            len(drifted) >= max(1, round(0.10 * len(features)))
            or any(c.startswith("curricular_units_1st_sem") for c in drifted)
        ),
        "features": features,
    }


def load_logs(path: Path) -> pd.DataFrame:
    """Extrae las features de los logs JSON del endpoint (event=inference)."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        record = json.loads(line)
        if record.get("event") == "inference":
            rows.extend(record.get("features", []))
    return pd.DataFrame(rows)


def simulate_shock(data: pd.DataFrame, n: int = 600, seed: int = 7) -> pd.DataFrame:
    """Lote sintético con un choque económico/académico (para demostrar el monitor).

    Sube el desempleo, baja la aprobación del 1er semestre y aumenta la
    proporción de estudiantes con deuda: el perfil que la pandemia produjo.
    """
    rng = np.random.default_rng(seed)
    batch = data.sample(n=n, random_state=seed).reset_index(drop=True).copy()
    batch["unemployment_rate"] = batch["unemployment_rate"] + rng.normal(3.0, 0.8, n)
    approved = batch["curricular_units_1st_sem_approved"]
    batch["curricular_units_1st_sem_approved"] = np.floor(approved * rng.uniform(0.4, 0.8, n))
    batch["curricular_units_1st_sem_grade"] = batch["curricular_units_1st_sem_grade"] * rng.uniform(0.6, 0.9, n)
    flip = rng.random(n) < 0.25
    batch.loc[flip, "debtor"] = 1
    batch.loc[flip, "tuition_fees_up_to_date"] = 0
    return batch


def to_markdown(report: dict, top: int = 10) -> str:
    lines = [
        "# Reporte de data drift",
        "",
        f"- Registros evaluados: **{report['n_current']}**",
        f"- Variables con drift significativo (PSI > {PSI_SIGNIFICANT}): **{len(report['drifted_features'])}**"
        f" de {report['n_features']}",
        f"- Reentrenamiento recomendado: **{'sí' if report['retrain_recommended'] else 'no'}**",
        "",
        "| Variable | PSI | KS | Media ref. | Media actual | Estado |",
        "|---|---|---|---|---|---|",
    ]
    ranked = sorted(report["features"].items(), key=lambda kv: -kv[1]["psi"])[:top]
    for name, f in ranked:
        lines.append(
            f"| {name} | {f['psi']:.3f} | {f['ks_statistic']:.3f} | {f['ref_mean']:.2f} "
            f"| {f['cur_mean']:.2f} | {f['status']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Detección de data drift (PSI + KS)")
    parser.add_argument("--reference", type=Path, required=True, help="reference_profile.json")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--current", type=Path, help="CSV con el lote actual")
    source.add_argument("--current-logs", type=Path, help="Logs JSON del endpoint")
    source.add_argument("--simulate-from", type=Path, help="CSV base para simular un choque")
    parser.add_argument("--output", type=Path, default=None, help="JSON del reporte")
    parser.add_argument("--markdown", type=Path, default=None, help="Resumen en Markdown")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args()

    profile = json.loads(args.reference.read_text())
    if args.current:
        current = pd.read_csv(args.current)
    elif args.current_logs:
        current = load_logs(args.current_logs)
    else:
        current = simulate_shock(pd.read_csv(args.simulate_from))

    if current.empty:
        print("Sin registros para evaluar")
        return

    report = drift_report(profile, current)
    summary = {k: v for k, v in report.items() if k != "features"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(report), encoding="utf-8")

    if args.fail_on_drift and report["retrain_recommended"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
