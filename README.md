# Proyecto Azure MLOps (P07)

**Plataforma MLOps: Entrenamiento e Inferencia de Modelos en Azure**

Reto académico avanzado (8 semanas) — Universidad Tecnológica de Bolívar.
Plataforma MLOps *end-to-end* sobre Microsoft Azure: infraestructura con **Terraform**,
pipelines de datos y entrenamiento con **Azure ML + MLflow**, empaquetado e inferencia
con **Docker + ACI**, y automatización con **Azure Pipelines**.

## Problema

Entrenar modelos en una notebook o en local no es producción. Se necesita una
plataforma repetible, versionada y operada que cubra el ciclo de vida completo de
un modelo:

1. **Infraestructura** manual → errores, inconsistencia y sin trazabilidad.
2. **Entrenamiento ad-hoc** → sin métricas, experimentos ni comparación de versiones.
3. **Modelos "en una carpeta"** → no se puede servir, versionar ni auditar.
4. **Sin CI/CD ni monitoreo** → no hay automatización, ni detección de drift ni observación.

El objetivo es construir, paso a paso, una plataforma MLOps real en Azure: infraestructura
como código, un pipeline de entrenamiento que registra el mejor modelo, un endpoint de
inferencia servido en la nube, y automatización + monitoreo del ciclo completo.

## Solución (en 4 etapas)

| # | Etapa | Semanas | Entregable |
|---|-------|---------|-----------|
| 1 | Infraestructura Base | 1-2  | Terraform: Storage, Key Vault, ACR, ML Workspace, Compute |
| 2 | Pipeline Datos + Train | 3-4 | Dataset, entrenamiento en compute, MLflow, Model Registry |
| 3 | Packaging + Inferencia | 5-6 | Docker, ACR push, deploy ACI, endpoint REST `/predict` |
| 4 | CI/CD + Monitoreo | 7-8 | Azure Pipelines MLOps, data drift, monitoreo, docs |

Flujo general:

```
CSV/JSON ──► Azure Blob Storage ──► Azure ML (Compute + MLflow + Model Registry)
                                          │
                       Model Packaging (Docker → ACR)
                                          │
        Azure Monitor ◄──────────────── ACI Endpoint (REST /predict)
```

> Diagrama de arquitectura interactivo (SVG, con vistas por etapa):
> abrir **`docs/architecture.html`** (generado con la skill *archify* desde
> `docs/architecture.json`).

## Estado del proyecto

| Etapa | Estado | Detalle |
|-------|--------|---------|
| 1. Infraestructura | ✅ **Desplegada** | Terraform aplicado en `centralus`, RG `rg-mlopsproj-dev` |
| 2. Datos + Train | ✅ **Completado** | Job `quirky_rain_j65rry7zny` → acc **0.8947**; `iris-classifier` v1 en **Production** |
| 3. Packaging + Inferencia | 🟡 **Código listo** | FastAPI verificada local + modelo descargado; build/push **bloqueado** (sin Docker) |
| 4. CI/CD + Monitoreo | ⏳ Pendiente | Azure Pipelines MLOps + drift + docs |

### Etapa 1 — Infraestructura (✅ desplegada)

La política `Allowed resource deployment regions` de la suscripción educativa solo
permite `centralus`, `brazilsouth`, `canadacentral`, `northcentralus`, `westus3`
(`eastus`/`eastus2` rechazados), por lo que todo se desplegó en **centralus**.

| Recurso | Nombre | Notas |
|---------|--------|-------|
| Resource Group | `rg-mlopsproj-dev` | `centralus` |
| Storage Account | `stmlopsprojdev001` | contenedores `raw` y `processed` |
| Key Vault | `kv-mlopsproj-dev` | secretos / credenciales |
| Container Registry | `acrmlopsprojdev` | login: `acrmlopsprojdev.azurecr.io`, admin habilitado |
| Log Analytics | `log-mlopsproj-dev` | |
| Application Insights | `appi-mlopsproj-dev` | |
| ML Workspace | `mlw-mlopsproj-dev` | |
| Compute cluster | `cpu-cluster` | `Standard_DS3_v2`, min 0 / max 4, **Succeeded** |

Suscripción: `Azure for Students` · Región: `centralus` ·
Terraform (v1.9.8 en `~/bin/terraform`) + Azure CLI (v2.83.0) + extension `ml`.

### Etapa 2 — Datos + Entrenamiento (✅ completado)

- **`ml/data/load_data.py`** genera `ml/data/iris.csv` (Iris, UCI/sklearn).
- **`ml/pipeline/modeling.py`**: lógica pura (load/split/train/evaluate/save).
- **`ml/pipeline/train.py`**: entrena `RandomForest` en el cluster, usa
  `mlflow.sklearn.autolog()` y registra el modelo fomentándolo de **Staging → Production**
  (compara contra `--baseline-accuracy 0.75`). No se llama `log_model` explícito porque
  el autolog ya registra el artefacto en `runs:/…/model` (causa conflicto).
- **`ml/pipeline/evaluate.py`**: evaluación resiliente MLflow 2.x / 3.x.
- **`ml/environments/conda.yaml`**: entorno del job, incluye `azureml-mlflow`
  (necesario para el plugin de Model Registry de Azure ML) y `mlflow>=2.9,<3` (API de stages).
- **`ml/pipeline/job.yaml`**: job `command` del workspace. Usa `code: ../../` (raíz,
  para que `python -m ml.pipeline.train` importe el paquete `ml`) y un input
  `uri_file` para el CSV.
- **6 tests unitarios** en `ml/tests/` (passing localmente).
- **Job en la nube**: experimento `iris-training`, job **`quirky_rain_j65rry7zny`**
  (**Completed**) → accuracy **0.8947**, modelo **`iris-classifier` v1 registrado en
  Model Registry con stage Production** (etiqueta de despliegue en Azure ML).
- Errores resueltos en el camino: `ModuleNotFoundError: ml` (faltaba subir el código de
  la raíz), registro fallido (faltaba el paquete `azureml-mlflow`) y conflicto de
  artefactos `model/` (duplicado de `log_model`).

### Etapa 3 — Packaging + Inferencia (🟡 código listo, servido pendiente)

- **`endpoint/app.py`**: FastAPI con `/health` y `/predict` (carga el modelo MLflow).
- **`endpoint/Dockerfile`**: base `mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest`,
  copia `model/` ya descargado.
- **`endpoint/download_model.sh`**: baja `iris-classifier` de Production del Model
  Registry a `endpoint/model/`.
- **Verificación local**: API probada en `127.0.0.1:8123` → `/health` OK, `/predict`
  → `setosa` (conf 1.0), `virginica`, y `400` con 3 features.
- **Bloqueo**: Docker no está instalado en la máquina (**`docker build/push` pendiente**)
  y ACR Tasks está bloqueado en la suscripción educativa (`TasksOperationsNotAllowed`).
  Instalación pendiente:
  ```bash
  sudo dnf install -y docker
  sudo systemctl enable --now docker
  sudo usermod -aG docker $USER
  ```
  Luego build + push (ver `endpoint/README.md`):
  ```bash
  cd endpoint
  az acr login --name acrmlopsprojdev
  docker build -t acrmlopsprojdev.azurecr.io/endpoint:latest .
  docker push acrmlopsprojdev.azurecr.io/endpoint:latest
  ```
  Despliegue en **ACI**: descomentar `azurerm_container_group` en `terraform/main.tf`
  y `terraform apply`, o el `az container create` documentado en `endpoint/README.md`.

### Etapa 4 — CI/CD + Monitoreo (⏳ pendiente)

- Azure Pipelines MLOps (`.azure-pipelines/`): data-prep → train → evaluate → deploy.
- Detección de data drift y monitoreo continuo (Azure Monitor + App Insights).
- Informe MLflow, documentación completa y análisis de costos.

## Estructura del repositorio

```
Proyecto_Azure_MLOps/
├── terraform/            # Infraestructura como código (Etapa 1 — desplegada)
│   └── main.tf, outputs.tf, variables.tf, providers.tf
├── ml/
│   ├── data/             # load_data.py + iris.csv generado
│   ├── pipeline/         # modeling.py, train.py, evaluate.py, job.yaml
│   ├── environments/     # conda.yaml (entorno del job Azure ML)
│   └── tests/            # 6 tests unitarios
├── endpoint/             # Etapa 3: FastAPI + Dockerfile + download_model.sh
├── .azure-pipelines/     # Pipeline MLOps CI/CD (Etapa 4)
└── docs/                 # architecture.html / architecture.json (diagrama)
```

## Cómo ejecutar (resumen)

### Entrenamiento en Azure ML (Etapa 2)

```bash
# Enviar el job con la config yaml (requiere workspace + compute de la Etapa 1)
az ml job create -f ml/pipeline/job.yaml --workspace-name mlw-mlopsproj-dev -g rg-mlopsproj-dev
```

### Inferencia local (Etapa 3, verificación)

```bash
cd endpoint
pip install -r requirements.txt
MODEL_PATH=$(pwd)/model uvicorn app:app --host 127.0.0.1 --port 8000
curl -s -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" \
  -d '{"features":[5.1,3.5,1.4,0.2]}'
# -> {"prediction":"setosa","confidence":1.0,"class_index":0}
```

### Pruebas unitarias

```bash
pytest ml/tests -v
```

> **MLflow y Model Registry**: se usa el API de *stages* (Staging → Production); solo
> existe en MLflow 2.x, por lo que `mlflow>=2.9,<3` está fijado. MLflow 2.x no instala
> en Python 3.14 local, pero funciona en el compute cluster de Azure ML. Los scripts son
> resilientes: `evaluate.py` soporta también MLflow 3.x.

## Siguientes pasos

1. Instalar Docker (comandos de arriba) y ejecutar build + push del endpoint a ACR.
2. Desplegar el endpoint en ACI y validar `/predict` contra el FQDN público.
3. Implementar la Etapa 4 (Azure Pipelines MLOps + monitoreo) en `.azure-pipelines/`.
4. Documentar resultados (informe MLflow), el diagrama de arquitectura y el análisis
   de costos en `docs/`.

## Criterios de evaluación

| Criterio | Peso |
|----------|------|
| Infraestructura Terraform desplegada | 20% |
| Pipeline entrenamiento con MLflow | 20% |
| Model Registry con promoción | 15% |
| Endpoint inferencia en ACI | 20% |
| Pipeline CI/CD MLOps | 15% |
| Monitoreo, documentación y costos | 10% |