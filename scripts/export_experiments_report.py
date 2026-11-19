"""Genera el informe de experimentos MLflow (docs/experimentos-mlflow.md).

Lee los runs del servidor de tracking activo (``MLFLOW_TRACKING_URI``: el
``mlruns.db`` local o el workspace de Azure ML) y escribe en Markdown:

- los runs de tuning (un run por combinación de hiperparámetros, con sus
  métricas de validación cruzada),
- los runs de entrenamiento (métricas de test, globales y por clase),
- el estado del Model Registry (versión y stage de cada modelo registrado).

Uso:
    # local
    $env:MLFLOW_TRACKING_URI = "sqlite:///mlruns.db"
    python scripts/export_experiments_report.py
    # Azure ML
    export MLFLOW_TRACKING_URI=$(az ml workspace show -n <ws> -g <rg> --query mlflow_tracking_uri -o tsv)
    python scripts/export_experiments_report.py --source "Azure ML (mlw-mlopslab-dev)"
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ["Dropout", "Enrolled", "Graduate"]


def _fmt(value, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in rows]
    return lines


def tuning_section(experiment: str, top: int) -> list[str]:
    runs = mlflow.search_runs(experiment_names=[experiment])
    if runs.empty or "metrics.cv_f1_macro" not in runs:
        return [f"_Sin runs en el experimento `{experiment}`._"]
    # los hijos son las combinaciones; el run padre solo resume el mejor
    runs = runs[runs["metrics.cv_f1_macro"].notna()].sort_values("metrics.cv_f1_macro", ascending=False)
    rows = [
        [
            i + 1,
            r["params.n_estimators"], r["params.max_depth"], r["params.min_samples_leaf"], r["params.class_weight"],
            r["metrics.cv_accuracy"], r["metrics.cv_f1_macro"], r["metrics.cv_f1_macro_std"],
            r["metrics.cv_recall_Dropout"], r["metrics.cv_recall_Enrolled"], r["metrics.cv_recall_Graduate"],
            f"`{r['run_id'][:8]}`",
        ]
        for i, (_, r) in enumerate(runs.head(top).iterrows())
    ]
    lines = [
        f"Experimento `{experiment}`: **{len(runs)} runs**, uno por combinación de hiperparámetros "
        f"(validación cruzada estratificada de 5 folds). Se muestran los {min(top, len(runs))} mejores por F1 macro.",
        "",
    ]
    lines += _table(
        ["#", "n_estimators", "max_depth", "min_samples_leaf", "class_weight",
         "CV accuracy", "CV F1 macro", "± std", "Recall Dropout", "Recall Enrolled", "Recall Graduate", "run"],
        rows,
    )
    best, worst = runs.iloc[0], runs.iloc[-1]
    lines += [
        "",
        f"Rango de F1 macro entre combinaciones: {worst['metrics.cv_f1_macro']:.4f} – "
        f"{best['metrics.cv_f1_macro']:.4f}. "
        f"Rango de recall de `Enrolled`: {runs['metrics.cv_recall_Enrolled'].min():.3f} – "
        f"{runs['metrics.cv_recall_Enrolled'].max():.3f}.",
    ]
    return lines


def training_section(experiment: str) -> list[str]:
    runs = mlflow.search_runs(experiment_names=[experiment])
    if runs.empty or "metrics.accuracy" not in runs:
        return [f"_Sin runs en el experimento `{experiment}`._"]
    runs = runs[runs["metrics.accuracy"].notna()].sort_values("start_time")
    rows = [
        [
            r["params.cfg_n_estimators"], r["params.cfg_max_depth"], r["params.cfg_min_samples_leaf"],
            r["params.cfg_class_weight"], r["metrics.accuracy"], r["metrics.f1_macro"],
            *[r.get(f"metrics.recall_{c}") for c in CLASSES],
            r.get("tags.class_thresholds_ok"), f"`{r['run_id'][:8]}`",
        ]
        for _, r in runs.iterrows()
    ]
    lines = [f"Experimento `{experiment}`: {len(runs)} runs, evaluados sobre el 20 % de test estratificado.", ""]
    lines += _table(
        ["n_estimators", "max_depth", "min_samples_leaf", "class_weight", "Accuracy", "F1 macro",
         *[f"Recall {c}" for c in CLASSES], "Umbrales por clase OK", "run"],
        rows,
    )
    return lines


def registry_section(model_name: str) -> list[str]:
    client = MlflowClient()
    try:
        versions = sorted(client.search_model_versions(f"name='{model_name}'"), key=lambda v: int(v.version))
    except Exception:
        versions = []
    if not versions:
        return [f"_El modelo `{model_name}` no está registrado._"]
    rows = []
    for v in versions:
        metrics = client.get_run(v.run_id).data.metrics
        stage = v.current_stage if v.current_stage not in (None, "None") else v.tags.get("stage", "—")
        rows.append([v.version, stage, metrics.get("accuracy"), metrics.get("f1_macro"), f"`{v.run_id[:8]}`"])
    return _table(["Versión", "Stage", "Accuracy", "F1 macro", "run"], rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Informe de experimentos MLflow en Markdown")
    parser.add_argument("--tuning-experiment", default="dropout-tuning")
    parser.add_argument("--training-experiment", default="enape-training")
    parser.add_argument("--model-name", default="enape-abandono")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--source", default=None, help="Texto que describe el servidor de tracking")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "experimentos-mlflow.md")
    args = parser.parse_args()

    source = args.source or f"MLflow local (`{mlflow.get_tracking_uri()}`)"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Informe de experimentos MLflow",
        "",
        f"Generado por `scripts/export_experiments_report.py` el {generated}. Fuente: {source}.",
        "",
        "Modelo: `RandomForestClassifier` sobre UCI 697 (4424 estudiantes, 36 variables, 3 clases).",
        "Cada run registra en MLflow sus hiperparámetros, métricas y artefactos (matriz de confusión,",
        "importancia de variables, perfil de referencia para drift y el modelo).",
        "",
        "## 1. Búsqueda de hiperparámetros",
        "",
        *tuning_section(args.tuning_experiment, args.top),
        "",
        "## 2. Entrenamientos candidatos",
        "",
        *training_section(args.training_experiment),
        "",
        "## 3. Model Registry",
        "",
        *registry_section(args.model_name),
        "",
        "Un candidato se registra en `Staging`; pasa a `Production` solo si supera el gate",
        "(`ml/pipeline/evaluate.py`): accuracy ≥ 0.70, recall mínimo por clase, accuracy mayor que la",
        "del modelo en Production y F1 macro sin retroceso.",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe escrito en {args.output}")


if __name__ == "__main__":
    main()
