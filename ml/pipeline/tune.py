"""Búsqueda de hiperparámetros del RandomForest con validación cruzada.

Cada combinación se registra como *run* anidado en MLflow para comparar en la
UI de experimentos. Criterio de selección (solo con datos de train, el test
queda reservado para la evaluación final de `train.py`):

1. Descartar combinaciones cuyo recall medio en CV incumpla los umbrales por
   clase de `modeling.DEFAULT_CLASS_THRESHOLDS` (Dropout >= 0.70, ...).
2. Entre las restantes, la de mayor F1 macro. No se usa accuracy: con clases
   desbalanceadas premia ignorar la clase Enrolled.

Uso:
    python -m ml.pipeline.tune --data ml/data/dropout.csv --tracking-uri sqlite:///mlruns.db
"""

import argparse
import itertools
import json
from pathlib import Path

import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import make_scorer, recall_score
from sklearn.model_selection import StratifiedKFold, cross_validate

from ml.pipeline.modeling import CLASSES, DEFAULT_CLASS_THRESHOLDS, load_data, split_data

GRID = {
    "n_estimators": [100, 300],
    "max_depth": [10, 15, None],
    "min_samples_leaf": [1, 3, 5],
    "class_weight": [None, "balanced_subsample"],
}

SCORING = {"f1_macro": "f1_macro", "accuracy": "accuracy"}
for _i, _name in enumerate(CLASSES):
    SCORING[f"recall_{_name}"] = make_scorer(recall_score, labels=[_i], average="macro")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tuning del RandomForest (CV 5-fold)")
    parser.add_argument("--data", type=Path, default=Path(__file__).parent.parent / "data/dropout.csv")
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--experiment", default="dropout-tuning")
    parser.add_argument("--output", type=Path, default=None, help="JSON con el ranking")
    args = parser.parse_args()

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)

    X_train, _, y_train, _ = split_data(load_data(args.data))
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)

    results = []
    keys = list(GRID)
    with mlflow.start_run(run_name="grid-search"):
        for values in itertools.product(*GRID.values()):
            params = dict(zip(keys, values))
            model = RandomForestClassifier(random_state=42, n_jobs=-1, **params)
            scores = cross_validate(model, X_train, y_train, cv=cv, scoring=SCORING)
            row = {**params}
            for metric in SCORING:
                row[f"cv_{metric}"] = round(float(scores[f"test_{metric}"].mean()), 4)
            row["cv_f1_macro_std"] = round(float(scores["test_f1_macro"].std()), 4)
            row["meets_thresholds"] = all(
                row[f"cv_recall_{name}"] >= minimum for name, minimum in DEFAULT_CLASS_THRESHOLDS.items()
            )
            with mlflow.start_run(nested=True):
                mlflow.log_params(params)
                mlflow.log_metrics({k: v for k, v in row.items() if k.startswith("cv_")})
            results.append(row)
            print(f"{params} -> F1 macro {row['cv_f1_macro']:.4f} "
                  f"recall Dropout {row['cv_recall_Dropout']:.3f} ok={row['meets_thresholds']}")

        results.sort(key=lambda r: (r["meets_thresholds"], r["cv_f1_macro"]), reverse=True)
        best = results[0]
        mlflow.log_dict({"ranking": results}, "tuning_ranking.json")
        mlflow.log_metric("best_cv_f1_macro", best["cv_f1_macro"])
        print(f"\nMejor combinación: {best}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
