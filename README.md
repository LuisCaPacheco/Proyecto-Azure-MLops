# Proyecto Azure MLOps (P07) — The Odyssey

**Plataforma MLOps en Azure para la predicción temprana de abandono escolar**

Reto académico avanzado (8 semanas) — Universidad Tecnológica de Bolívar.
Plataforma MLOps *end-to-end* sobre Microsoft Azure: infraestructura con **Terraform**,
pipelines de datos y entrenamiento con **Azure ML + MLflow**, empaquetado e inferencia
con **Docker + ACI**, y automatización + monitoreo con **Azure Pipelines**.

## Problema

Abandonar los estudios sin completar el nivel en curso es una de las mayores
fuentes de desigualdad educativa en América Latina, y las intervenciones suelen
llegar cuando el estudiante ya se fue. El modelo estima, con variables
observables **antes** de cursar el ciclo, la probabilidad de que un estudiante no
se reinscriba (`Abandona`) o continúe (`Continua`), y explica qué factores pesan
en el riesgo para orientar la intervención.

Dataset: **ENAPE 2021 — Encuesta Nacional de Acceso y Permanencia en la
Educación** (INEGI, México). Archivo `df03_Dataset_ENAPE.csv` (32.343 registros ×
67 columnas). Tras aplicar la cohorte de estudio quedan **18.207 estudiantes**,
con **6,48 % de abandono** (1.179 casos).

## Solución (en 4 etapas)

| # | Etapa | Semanas | Entregable |
|---|-------|---------|-----------|
| 1 | Infraestructura Base | 1-2  | Terraform: Storage, Key Vault, ACR, ML Workspace, Compute |
| 2 | Pipeline Datos + Train | 3-4 | Dataset, entrenamiento en compute, MLflow, Model Registry |
| 3 | Packaging + Inferencia | 5-6 | Docker, ACR push, deploy ACI, endpoint REST `/predict` |
| 4 | CI/CD + Monitoreo | 7-8 | Azure Pipelines MLOps, data drift, monitoreo, docs |

```
ENAPE CSV ─► load_enape.py ─► validate.py ─► Blob (raw) ─► Azure Data Factory ─► Blob (processed)
                                                              └─► raw/rejected (filas descartadas)
Blob (processed) ─► Azure ML job (cpu-cluster + MLflow) ─► Model Registry (Staging)
                                                                      │
              gate: PR-AUC ≥ 0.35 y recall Abandona ≥ 0.60 ─► download_model.sh ─► Docker ─► ACR
                                                                      │
                             ACI + smoke test ─► promote.py (Staging → Production)
                                                                      │
        Bienestar Univ. ──X-API-Key──► ACI /predict /explain ──logs JSON──► Log Analytics
                                                                      │
                             drift-monitoring.yml (diario, PSI + KS) ─┘─► reentrenamiento
```

> Diagrama de arquitectura interactivo: **`docs/architecture.html`**.

## Estado del proyecto (2026-11-18)

| Etapa | Estado | Detalle |
|-------|--------|---------|
| 1. Infraestructura | ✅ **Desplegada y verificada** (17-11) | 27 recursos gestionados por Terraform en `rg-mlopslab-dev`; `terraform plan` sin cambios. |
| 2. Datos + Train | ✅ **Dataset migrado a ENAPE y modelo validado en local** | Cohorte de 18.207 filas, validación `ok`; `enape-abandono` con ROC-AUC 0.862 / PR-AUC 0.404 / recall 0.712 y gate superado. La corrida real en Azure se relanza el 19-11. |
| 3. Packaging + Inferencia | ✅ **Endpoint probado contra Azure** (17-11) | `endpoint:v1` y `v2` en ACR; 4/4 pruebas: `/health` 200, `/predict` 401 sin key, predicción con key, `/feedback` 202. Se reconstruye como `v3` con el modelo ENAPE. |
| 4. CI/CD + Monitoreo | 🟡 **Definido, sin ejecutar** | 3 alertas, action group y workbook desplegados y verificados; los YAML de Azure Pipelines esperan *service connection* ARM y *variable group*. |

> **El entorno se apagó y eliminó el 2026-11-18** para no seguir consumiendo
> crédito: 0 recursos en `rg-mlopslab-dev` (ACR y Key Vault incluidos). Se
> conserva el state remoto en `rg-tfstate-mlops` para recrear todo con
> `scripts/azure_up.ps1 -Stage all -ImageTag v3`.
>
> Documentación: **`docs/guia-tecnica.md`** (mapa técnico: qué hace cada archivo
> de Terraform y dónde mirar en Azure), `docs/despliegue-azure.md` (runbook por
> etapas), `docs/preguntas-defensa.md` (preguntas probables y decisiones),
> `docs/dashboard.html` (resumen de la corrida),
> `docs/demo-curl-azure.md` (evidencia del endpoint),
> `docs/cumplimiento-brief.md` (rúbrica) y `docs/costos.md`.

### Resultados del modelo ENAPE (test estratificado 20 %, 3.642 estudiantes)

| Métrica | Valor | Umbral del gate |
|---|---|---|
| ROC-AUC | **0.862** | — |
| PR-AUC | **0.404** | ≥ 0.35 |
| Recall `Abandona` | **0.712** | ≥ 0.60 |
| F1 macro | 0.656 | — |
| Exactitud | 0.858 | — |

Por clase: `Continua` precision 0.978 / recall 0.868 / F1 0.919 (3.406 casos);
`Abandona` precision 0.272 / recall 0.712 / F1 0.393 (236 casos). La precisión
baja es deliberada: con `class_weight="balanced_subsample"` el modelo privilegia
detectar abandonos, que es lo que permite intervenir a tiempo.

Detalle en `outputs/metrics_enape.json` y `outputs/evaluation/` (matriz de
confusión, importancia de variables, perfil de drift).

Las cifras de la corrida histórica con UCI 697 (accuracy 0.7571, F1 0.7002)
quedan como evidencia en `docs/despliegue-azure.md`; el modelo
`dropout-classifier` v1 se conserva en el registry como historial.

### Etapa 1 — Infraestructura

| Recurso | Nombre | Notas |
|---------|--------|-------|
| Resource Group | `rg-mlopslab-dev` | `centralus` (única región permitida con eastus bloqueado) |
| Storage Account | `stmlopslabdev001` | contenedores `raw` y `processed` |
| Key Vault | `kv-mlopslab-dev` | secreto `endpoint-api-key` generado por Terraform |
| Container Registry | `acrmlopslabdev` | `acrmlopslabdev.azurecr.io` |
| Log Analytics / App Insights | `log-` / `appi-mlopslab-dev` | logs de inferencia y telemetría |
| ML Workspace | `mlw-mlopslab-dev` | |
| Compute cluster | `cpu-cluster` | `Standard_DS3_v2`, min 0 / max 2 — en Terraform (`training.tf`) |
| Datastores Azure ML | `raw_data`, `processed_data` | sobre los contenedores `raw` / `processed` (`training.tf`) |
| Data Factory | `adf-mlopslab-dev` | pipeline `pl_clean_enape` + Data Flow `df_clean_enape` (`datafactory.tf`) |
| Estado de Terraform | backend `azurerm` | remoto (`sttfstatemlopslab`), creado por `scripts/azure_up.ps1 -Stage state` |
| ACI (inferencia) | `aci-mlopslab-dev-inference` | Terraform es el único dueño; `scripts/azure_up.ps1 -Stage aci -ImageTag v3` |
| Alertas | `ag-`, `alert-…-aci-cpu`, `alert-…-endpoint-errors` | Azure Monitor |

### Etapa 2 — Datos + Entrenamiento

- `ml/data/load_enape.py`: aplica la cohorte de estudio, deriva la etiqueta binaria, renombra al contrato snake_case y recodifica binarios 1/2 → 1/0.
- `ml/data/load_data.py`: loader del dataset UCI 697 anterior; queda como legado.
- `ml/data/validate.py`: validación estructural (esquema, tipos, mínimo de filas, clases con representación) y conteo de filas inválidas o duplicadas; detiene el pipeline si el archivo no es el dataset esperado.
- `ml/data/upload_to_blob.sh`: sube el CSV a `raw/enape/`.
- `ml/data/run_adf_pipeline.sh`: ejecuta el pipeline de **Azure Data Factory** (`raw` → `processed`: aplica cohorte, descarta filas inválidas y duplicadas, las rechazadas van a `raw/rejected/enape/`) y registra la salida como Data Asset `enape-abandono`.
- `ml/pipeline/tune.py`: grid de 36 combinaciones, CV 5-fold; elige el mejor F1 macro que cumpla los umbrales de recall por clase (runs anidados en MLflow).
- `ml/pipeline/train.py`: entrena, registra en MLflow parámetros, métricas por clase, matriz de confusión, importancia de variables y el **perfil de referencia para drift**; registra `enape-abandono` en **Staging** (el entrenamiento nunca promueve).
- `ml/pipeline/evaluate.py`: gate del CI/CD. Aprueba solo si **PR-AUC ≥ 0.35**, **recall de `Abandona` ≥ 0.60**, sin retroceso de PR-AUC frente a Production y con una versión distinta a la desplegada.
- `ml/pipeline/promote.py`: Staging → Production (y la versión anterior a Archived); se ejecuta después del smoke test del despliegue, así Production es siempre lo que sirve el endpoint.
- `ml/pipeline/job.yaml`: job de Azure ML con los hiperparámetros ganadores.

### Etapa 3 — Endpoint

- `endpoint/app.py`: FastAPI. `GET /health`, `GET /model-info`, `POST /predict`, `POST /predict/batch`, `POST /explain`, `POST /feedback`.
- Acepta las **18 variables** del contrato (vector ordenado o diccionario); el modelo usa 16 y descarta `max_nivel_esp` / `entr_diagnost` por fuga estructural.
- Cada predicción devuelve un `prediction_id`; con `POST /feedback` se reporta después la clase real del estudiante, que alimenta el monitoreo de accuracy.
- Respuesta: clase, probabilidades, `dropout_risk` (P(Abandona)) y `risk_level` (alto ≥ 0.5, medio ≥ 0.3, bajo).
- `endpoint/explain.py`: contribución de cada variable a P(Abandona) (descomposición por caminos de los árboles; base + contribuciones = probabilidad exacta).
- Seguridad: `X-API-Key` (desde Key Vault), rate limiting por IP, usuario no-root, entradas validadas y claves desconocidas rechazadas.
- Telemetría: log JSON por inferencia (stdout → Log Analytics) + Application Insights opcional.
- Imagen `python:3.12-slim` (≈ 0.8 GB), sin MLflow: lee el MLmodel + cloudpickle directamente.

### Etapa 4 — CI/CD + Monitoreo

- `.azure-pipelines/azure-pipelines.yml`: CI (flake8 + pytest) → DataPrep (validar + Data Factory) → Train (job Azure ML, Staging) → Evaluate (gate vs Production) → Build & Push (ACR) → Deploy (ACI, con aprobación manual) → smoke test → promoción a Production.
- `.azure-pipelines/drift-monitoring.yml`: diario; lee inferencias de Log Analytics, calcula PSI + KS contra el perfil de referencia y lanza reentrenamiento si hay drift.
- `ml/monitoring/drift.py`: sin drift sobre la población original; con un choque simulado detecta las variables desplazadas y recomienda reentrenar.
- `ml/monitoring/performance.py`: accuracy decay. Cruza predicciones y feedback por `prediction_id`, compara la accuracy observada con la de referencia y recomienda reentrenar si cae más de 5 puntos o si el recall de una clase baja de su umbral.
- `terraform/monitoring.tf`: alerta de latencia P99 y Workbook de Azure Monitor (volumen, niveles de riesgo, latencia P50/P95/P99, accuracy observada).
- `docs/experimentos-mlflow.md`: informe de experimentos (runs de tuning + entrenamientos + Model Registry), generado con `scripts/export_experiments_report.py`.
- `docs/costos.md`: análisis de costos (≈ USD 20/mes con ACI en horario laboral), con la comparación CPU vs GPU de entrenamiento frente al costo de inferencia.
- `docs/dashboard.html`: panel autocontenido con el estado real del despliegue (dataset, métricas, verificación del endpoint, inventario y estado del entorno). Se regenera con `scripts/build_dashboard.ps1`.

## Estructura del repositorio

```
Proyecto-Azure-MLops-main/
├── archive (1)/          # ENAPE 2021 crudo (INEGI)
├── terraform/            # main.tf, training.tf (cluster, datastores), datafactory.tf (ETL),
│                         # inference.tf (ACI, Key Vault secret, RBAC, alertas), monitoring.tf
├── ml/
│   ├── data/             # load_enape.py, validate.py, upload_to_blob.sh, run_adf_pipeline.sh, enape.csv
│   ├── pipeline/         # modeling.py, tune.py, train.py, evaluate.py, promote.py, reporting.py, job.yaml
│   ├── monitoring/       # drift.py (PSI + KS), performance.py (accuracy decay)
│   ├── environments/     # conda.yaml (job Azure ML)
│   └── tests/            # pruebas unitarias
├── endpoint/             # app.py, explain.py, Dockerfile, download_model.sh, model/, tests/, examples/
├── .azure-pipelines/     # azure-pipelines.yml, drift-monitoring.yml
├── scripts/              # azure_up.ps1, run_local_pipeline.ps1, export_production_model.py,
│                         # export_local_model.py, make_examples.py, snapshot_azure.ps1, build_dashboard.ps1
└── docs/                 # dashboard.html, guia-tecnica.md, despliegue-azure.md, costos.md, cumplimiento-brief.md
```

## Cómo ejecutar

### Todo en local (Windows)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r ml\requirements-local.txt
python -m ml.data.load_enape                 # genera ml/data/enape.csv (18.207 filas)
powershell -ExecutionPolicy Bypass -File scripts\run_local_pipeline.ps1 -Clean
.venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlruns.db   # http://127.0.0.1:5000
```

Para regenerar el modelo que se hornea en la imagen sin Azure:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.venv\Scripts\python -m ml.pipeline.train --skip-register --output outputs/model `
  --metrics-output outputs/metrics_enape.json --tracking-uri sqlite:///mlruns.db
.venv\Scripts\python scripts\export_local_model.py
.venv\Scripts\python scripts\make_examples.py
```

### Endpoint en Docker

```powershell
cd endpoint
docker build -t enape-api:local .
docker run -d -p 8000:8000 -e API_KEY=mi-clave enape-api:local
curl.exe -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" `
  -H "X-API-Key: mi-clave" -d "@examples/estudiante_riesgo_alto.json"
```

### Azure por etapas (con confirmación)

Requiere `az login` y, para imagen/ACI, Docker Desktop. Cada etapa es
idempotente y se lanza a mano para no consumir crédito sin querer:

```powershell
.\scripts\azure_up.ps1 -Stage preflight            # az/terraform/docker, suscripción y cuota
.\scripts\azure_up.ps1 -Stage state                # storage account del tfstate
.\scripts\azure_up.ps1 -Stage base                 # infraestructura sin ACI
.\scripts\azure_up.ps1 -Stage data                 # CSV -> Blob -> ADF -> Data Asset
.\scripts\azure_up.ps1 -Stage train                # job Azure ML (registra en Staging)
.\scripts\azure_up.ps1 -Stage image -ImageTag v3   # descarga el modelo y publica en ACR
.\scripts\azure_up.ps1 -Stage aci   -ImageTag v3   # terraform apply del ACI
.\scripts\azure_up.ps1 -Stage verify               # /health, 401, /predict, /feedback
.\scripts\azure_up.ps1 -Stage stop                 # detiene el ACI (ahorra crédito)
.\scripts\azure_up.ps1 -Stage destroy              # borra todo (pide confirmación)
```

O todo seguido con `.\scripts\azure_up.ps1 -Stage all -ImageTag v3` (~30-45 min).
Guía completa, costos y solución de problemas: **`docs/despliegue-azure.md`**.

### Panel de pruebas

```powershell
pwsh -File scripts/build_dashboard.ps1     # lee Azure CLI y corre pytest
```

Abre `docs/dashboard.html`: estado del entorno, dataset, métricas del modelo,
verificación del endpoint e inventario de recursos.

### Entrenamiento en Azure ML (manual)

```bash
bash ml/data/upload_to_blob.sh                      # CSV -> raw
bash ml/data/run_adf_pipeline.sh                    # ADF: raw -> processed + Data Asset
az ml job create -f ml/pipeline/job.yaml --set inputs.data.path=azureml:enape-abandono@latest \
  --workspace-name mlw-mlopslab-dev -g rg-mlopslab-dev
```

## Pendientes para el cierre

Desplegado el 2026-11-17 en `rg-mlopslab-dev` (27 recursos en Terraform, job de
entrenamiento y ACI verificados) y eliminado el 18-11 para no consumir crédito.
Lo que queda:

1. **Relanzar con ENAPE**: `-Stage all -ImageTag v3` (data → train → image → aci → verify → stop), presupuesto ~0,2–0,35 USD.
2. En Azure DevOps: service connection ARM, variable group vinculado a Key Vault y los dos pipelines (`azure-pipelines.yml`, `drift-monitoring.yml`).
3. Validar el gate y la promoción Staging → Production contra el workspace real.
4. Subir ≥ 5 runs de MLflow al workspace de Azure (los de tuning están en local).
5. VNet + private endpoints y HTTPS (Application Gateway o Front Door delante del ACI).

## Criterios de evaluación

| Criterio | Peso |
|----------|------|
| Infraestructura Terraform desplegada | 20% |
| Pipeline entrenamiento con MLflow | 20% |
| Model Registry con promoción | 15% |
| Endpoint inferencia en ACI | 20% |
| Pipeline CI/CD MLOps | 15% |
| Monitoreo, documentación y costos | 10% |

Contraste requisito por requisito con el brief: **`docs/cumplimiento-brief.md`**.
