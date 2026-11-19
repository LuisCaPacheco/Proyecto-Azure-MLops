# Informe de experimentos MLflow

> **Nota (2026-11-18).** Este informe corresponde a la búsqueda de
> hiperparámetros sobre el dataset **UCI 697** (corrida del 14-11) y se conserva
> como historial. El dataset vigente es **ENAPE 2021**; sus métricas están en
> `outputs/metrics_enape.json`, en el `README.md` y en `docs/dashboard.html`.
> Para regenerar este informe con los runs actuales:
> `python scripts/export_experiments_report.py`.

Generado por `scripts/export_experiments_report.py` el 2026-11-14 21:06 UTC. Fuente: MLflow local (run_local_pipeline.ps1, 2026-11-14).

Modelo: `RandomForestClassifier` sobre UCI 697 (4424 estudiantes, 36 variables, 3 clases).
Cada run registra en MLflow sus hiperparámetros, métricas y artefactos (matriz de confusión,
importancia de variables, perfil de referencia para drift y el modelo).

## 1. Búsqueda de hiperparámetros

Experimento `dropout-tuning`: **36 runs**, uno por combinación de hiperparámetros (validación cruzada estratificada de 5 folds). Se muestran los 15 mejores por F1 macro.

| # | n_estimators | max_depth | min_samples_leaf | class_weight | CV accuracy | CV F1 macro | ± std | Recall Dropout | Recall Enrolled | Recall Graduate | run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 300 | 10 | 3 | balanced_subsample | 0.7652 | 0.7164 | 0.0123 | 0.7229 | 0.5559 | 0.8676 | `4c8892bf` |
| 2 | 300 | None | 3 | balanced_subsample | 0.7751 | 0.7132 | 0.0152 | 0.7493 | 0.4614 | 0.9043 | `c6c65b46` |
| 3 | 100 | 10 | 3 | balanced_subsample | 0.7607 | 0.7124 | 0.0151 | 0.7203 | 0.5559 | 0.8602 | `d91f6502` |
| 4 | 300 | 15 | 3 | balanced_subsample | 0.7731 | 0.7123 | 0.0136 | 0.7441 | 0.4693 | 0.9010 | `2f66c0a8` |
| 5 | 100 | 15 | 3 | balanced_subsample | 0.7714 | 0.7119 | 0.0180 | 0.7405 | 0.4787 | 0.8964 | `37143bab` |
| 6 | 300 | 10 | 5 | balanced_subsample | 0.7581 | 0.7117 | 0.0153 | 0.7133 | 0.5685 | 0.8551 | `f21e05b9` |
| 7 | 300 | None | 5 | balanced_subsample | 0.7638 | 0.7116 | 0.0118 | 0.7291 | 0.5228 | 0.8727 | `24b87c73` |
| 8 | 300 | 15 | 5 | balanced_subsample | 0.7618 | 0.7101 | 0.0145 | 0.7247 | 0.5276 | 0.8698 | `7d1cc3b3` |
| 9 | 300 | 10 | 1 | balanced_subsample | 0.7641 | 0.7086 | 0.0172 | 0.7247 | 0.5055 | 0.8823 | `8eca3ec1` |
| 10 | 100 | 15 | 5 | balanced_subsample | 0.7604 | 0.7078 | 0.0110 | 0.7229 | 0.5244 | 0.8693 | `17e8e521` |
| 11 | 100 | 10 | 5 | balanced_subsample | 0.7547 | 0.7076 | 0.0139 | 0.7098 | 0.5638 | 0.8523 | `ff6c5ddc` |
| 12 | 100 | None | 3 | balanced_subsample | 0.7697 | 0.7072 | 0.0177 | 0.7423 | 0.4598 | 0.8987 | `4d081f8f` |
| 13 | 100 | 10 | 1 | balanced_subsample | 0.7595 | 0.7033 | 0.0222 | 0.7247 | 0.4961 | 0.8766 | `21d1a81d` |
| 14 | 100 | 15 | 1 | balanced_subsample | 0.7773 | 0.7024 | 0.0153 | 0.7555 | 0.3843 | 0.9326 | `f5a69a06` |
| 15 | 300 | 15 | 1 | balanced_subsample | 0.7751 | 0.7022 | 0.0165 | 0.7555 | 0.3906 | 0.9259 | `b660473d` |

Rango de F1 macro entre combinaciones: 0.6630 – 0.7164. Rango de recall de `Enrolled`: 0.263 – 0.569.

## 2. Entrenamientos candidatos

Experimento `dropout-training`: 2 runs, evaluados sobre el 20 % de test estratificado.

| n_estimators | max_depth | min_samples_leaf | class_weight | Accuracy | F1 macro | Recall Dropout | Recall Enrolled | Recall Graduate | Umbrales por clase OK | run |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 10 | 5 | None | 0.7695 | 0.6787 | 0.7570 | 0.3019 | 0.9457 | False | `0ac4c218` |
| 300 | 10 | 3 | balanced_subsample | 0.7424 | 0.6990 | 0.6725 | 0.6038 | 0.8371 | True | `6da279cd` |

## 3. Model Registry

| Versión | Stage | Accuracy | F1 macro | run |
|---|---|---|---|---|
| 1 | Staging | 0.7695 | 0.6787 | `0ac4c218` |
| 2 | Production | 0.7424 | 0.6990 | `6da279cd` |

Un candidato se registra en `Staging`; pasa a `Production` solo si supera el gate
(`ml/pipeline/evaluate.py`): accuracy ≥ 0.70, recall mínimo por clase, accuracy mayor que la
del modelo en Production y F1 macro sin retroceso.
