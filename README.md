# Proyecto Azure MLOps (P07) — The Odyssey

**Plataforma MLOps en Azure para la predicción temprana de deserción universitaria**

Reto académico avanzado (8 semanas) — Universidad Tecnológica de Bolívar.
Plataforma MLOps *end-to-end* sobre Microsoft Azure: infraestructura con **Terraform**,
pipelines de datos y entrenamiento con **Azure ML + MLflow**, empaquetado e inferencia
con **Docker + ACI**, y automatización + monitoreo con **Azure Pipelines**.

## Problema

La deserción en pregrado en Colombia ronda el 45–50 % (MEN / SPADIES) y Bienestar
Universitario suele intervenir tarde. El modelo estima, con datos académicos y
socioeconómicos, la probabilidad de que un estudiante abandone (`Dropout`), siga
matriculado (`Enrolled`) o se gradúe (`Graduate`), y explica qué factores empujan
el riesgo para orientar la intervención.

Dataset: **UCI 697 — Predict Students' Dropout and Academic Success**
(4424 estudiantes, 36 variables, 3 clases: Graduate 50 %, Dropout 32 %, Enrolled 18 %).

## Solución (en 4 etapas)

| # | Etapa | Semanas | Entregable |
|---|-------|---------|-----------|
| 1 | Infraestructura Base | 1-2  | Terraform: Storage, Key Vault, ACR, ML Workspace, Compute |
| 2 | Pipeline Datos + Train | 3-4 | Dataset, entrenamiento en compute, MLflow, Model Registry |
| 3 | Packaging + Inferencia | 5-6 | Docker, ACR push, deploy ACI, endpoint REST `/predict` |
| 4 | CI/CD + Monitoreo | 7-8 | Azure Pipelines MLOps, data drift, monitoreo, docs |

```
UCI CSV ─► Blob Storage (raw) ─► Azure ML job (cpu-cluster + MLflow) ─► Model Registry (Production)
                                                                              │
                                        download_model.sh ─► Docker (FastAPI) ─► ACR
                                                                              │
Bienestar Univ. ──X-API-Key──► ACI /predict /explain ──logs JSON──► Log Analytics / App Insights
                                                                              │
                                     drift-monitoring.yml (diario, PSI + KS) ─┘─► reentrenamiento
```

> Diagrama de arquitectura interactivo: **`docs/architecture.html`**.

## Estado del proyecto (segundo corte)

| Etapa | Estado | Detalle |
|-------|--------|---------|
| 1. Infraestructura | ✅ **Desplegada** | Terraform aplicado en `centralus`, RG `rg-mlopsproj-dev`; ampliado con ACI, Key Vault secret, RBAC y alertas (`inference.tf`, validado) |
| 2. Datos + Train | ✅ **Migrado a deserción** | Dataset UCI 697, tuning CV, métricas por clase, gate de promoción; `dropout-classifier` v2 en Production (MLflow local) |
| 3. Packaging + Inferencia | ✅ **Imagen construida y probada** | FastAPI con API key, rate limit, `/predict`, `/predict/batch`, `/explain`; contenedor Docker *healthy* en local; falta `docker push` + ACI (credenciales Azure) |
| 4. CI/CD + Monitoreo | 🟡 **Código listo** | `azure-pipelines.yml` (CI → DataPrep → Train → Gate → Build → Deploy) y `drift-monitoring.yml` (PSI + KS diario); falta conectarlos en Azure DevOps |

### Resultados del modelo (test estratificado 20 %, 885 estudiantes)

| Versión | Configuración | Accuracy | F1 macro | Recall Dropout | Recall Enrolled | Recall Graduate | Gate |
|---|---|---|---|---|---|---|---|
| v1 | RF 100 árboles, prof. 10, hoja 5, sin balanceo (propuesta) | 0.7695 | 0.679 | 0.757 | **0.302** | 0.946 | ❌ Enrolled < 0.40 |
| v2 | RF 300 árboles, prof. 10, hoja 3, `balanced_subsample` (tuning) | 0.7424 | **0.699** | 0.673 | **0.604** | 0.837 | ✅ Production |

La v1 reproduce el 0.7685 de la propuesta, pero casi ignora a los estudiantes `Enrolled`
(detecta 3 de cada 10). La v2, elegida por validación cruzada (F1 macro 0.716 ± 0.012),
sacrifica 2.7 puntos de accuracy para duplicar el recall de esa clase. Detalle en
`outputs/evaluation/` (métricas, matriz de confusión, importancia de variables).

### Etapa 1 — Infraestructura

| Recurso | Nombre | Notas |
|---------|--------|-------|
| Resource Group | `rg-mlopsproj-dev` | `centralus` (única región permitida con eastus bloqueado) |
| Storage Account | `stmlopsprojdev001` | contenedores `raw` y `processed` |
| Key Vault | `kv-mlopsproj-dev` | secreto `endpoint-api-key` (nuevo, generado por Terraform) |
| Container Registry | `acrmlopsprojdev` | `acrmlopsprojdev.azurecr.io` |
| Log Analytics / App Insights | `log-` / `appi-mlopsproj-dev` | logs de inferencia y telemetría |
| ML Workspace | `mlw-mlopsproj-dev` | |
| Compute cluster | `cpu-cluster` | `Standard_DS3_v2`, min 0 / max 4 |
| ACI (nuevo, opcional) | `aci-mlopsproj-dev-inference` | `terraform apply -var="deploy_aci=true"` |
| Alertas (nuevo) | `ag-`, `alert-…-aci-cpu`, `alert-…-endpoint-errors` | Azure Monitor |

### Etapa 2 — Datos + Entrenamiento

- `ml/data/load_data.py`: descarga UCI 697, normaliza columnas y codifica la clase.
- `ml/data/upload_to_blob.sh`: sube a `raw/` y registra el Data Asset `student-dropout`.
- `ml/pipeline/tune.py`: grid de 36 combinaciones, CV 5-fold; elige el mejor F1 macro que cumpla los umbrales de recall por clase (runs anidados en MLflow).
- `ml/pipeline/train.py`: entrena, registra en MLflow parámetros, métricas por clase, matriz de confusión, importancia de variables y el **perfil de referencia para drift**; registra `dropout-classifier` y lo promueve a Production solo si accuracy ≥ 0.70 **y** recall Dropout ≥ 0.65, Enrolled ≥ 0.40, Graduate ≥ 0.80.
- `ml/pipeline/evaluate.py`: gate del CI/CD (baseline + recall por clase + F1 macro vs Production).
- `ml/pipeline/job.yaml`: job de Azure ML con los hiperparámetros ganadores.

### Etapa 3 — Endpoint

- `endpoint/app.py`: FastAPI. `GET /health`, `GET /model-info`, `POST /predict`, `POST /predict/batch`, `POST /explain`.
- Respuesta: clase, probabilidades, `dropout_risk` y `risk_level` (alto ≥ 0.5, medio ≥ 0.3, bajo).
- `endpoint/explain.py`: contribución de cada variable a P(Dropout) (descomposición por caminos de los árboles; base + contribuciones = probabilidad exacta).
- Seguridad: `X-API-Key` (desde Key Vault), rate limiting por IP, usuario no-root, entradas validadas.
- Telemetría: log JSON por inferencia (stdout → Log Analytics) + Application Insights opcional.
- Imagen `python:3.12-slim` (≈ 0.8 GB), sin MLflow: lee el MLmodel + cloudpickle directamente.

### Etapa 4 — CI/CD + Monitoreo

- `.azure-pipelines/azure-pipelines.yml`: CI (flake8 + pytest) → DataPrep → Train (job Azure ML) → Evaluate (gate) → Build & Push (ACR) → Deploy (ACI, con aprobación manual) → smoke test.
- `.azure-pipelines/drift-monitoring.yml`: diario; lee inferencias de Log Analytics, calcula PSI + KS contra el perfil de referencia y lanza reentrenamiento si hay drift.
- `ml/monitoring/drift.py`: demostrado localmente — sin drift sobre la población original; con un choque simulado (desempleo +3 pts, menos materias aprobadas, más deudores) detecta 4 variables y recomienda reentrenar.
- `docs/costos.md`: análisis de costos (≈ USD 20/mes con ACI en horario laboral).

## Estructura del repositorio

```
Proyecto-Azure-MLops-main/
├── terraform/            # main.tf (Etapa 1) + inference.tf (ACI, Key Vault secret, RBAC, alertas)
├── ml/
│   ├── data/             # load_data.py, upload_to_blob.sh, dropout.csv
│   ├── pipeline/         # modeling.py, tune.py, train.py, evaluate.py, reporting.py, job.yaml
│   ├── monitoring/       # drift.py (PSI + KS)
│   ├── environments/     # conda.yaml (job Azure ML)
│   └── tests/            # 16 pruebas unitarias
├── endpoint/             # app.py, explain.py, Dockerfile, download_model.sh, tests/ (12), examples/
├── .azure-pipelines/     # azure-pipelines.yml, drift-monitoring.yml
├── scripts/              # run_local_pipeline.ps1, export_production_model.py, make_examples.py
└── docs/                 # architecture.html, costos.md
```

## Cómo ejecutar

### Todo en local (Windows)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r ml\requirements-local.txt
powershell -ExecutionPolicy Bypass -File scripts\run_local_pipeline.ps1 -Clean
.venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlruns.db   # http://127.0.0.1:5000
```

### Endpoint en Docker

```powershell
cd endpoint
docker build -t dropout-api:local .
docker run -d -p 8000:8000 -e API_KEY=mi-clave dropout-api:local
curl.exe -X POST http://127.0.0.1:8000/explain -H "Content-Type: application/json" `
  -H "X-API-Key: mi-clave" -d "@examples/estudiante_riesgo_alto.json"
```

### Entrenamiento en Azure ML

```bash
bash ml/data/upload_to_blob.sh
az ml job create -f ml/pipeline/job.yaml --set inputs.data.path=azureml:student-dropout@latest \
  --workspace-name mlw-mlopsproj-dev -g rg-mlopsproj-dev --stream
```

### Publicar y desplegar

```bash
cd endpoint && ./download_model.sh
az acr login -n acrmlopsprojdev
docker build -t acrmlopsprojdev.azurecr.io/endpoint:v2 . && docker push acrmlopsprojdev.azurecr.io/endpoint:v2
cd ../terraform && terraform init -upgrade && terraform apply -var="deploy_aci=true" -var="endpoint_image_tag=v2"
```

## Pendientes para el cierre

1. `az login` con la cuenta del equipo → subir datos, correr `job.yaml` en el cluster y registrar v2 en el workspace.
2. `docker push` a ACR y `terraform apply -var="deploy_aci=true"`; validar `/predict` contra el FQDN.
3. Crear en Azure DevOps la service connection, el variable group vinculado a Key Vault y los dos pipelines.
4. Dashboard (Azure Workbook / Power BI) sobre Log Analytics con volumen de inferencias y niveles de riesgo.
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
