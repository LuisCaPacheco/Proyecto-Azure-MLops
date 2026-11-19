# Cumplimiento del brief P07

Contraste entre `Docs/P07_Plataforma_MLOps_Azure (2).docx` y lo implementado en
el repositorio, más lo **ejecutado contra Azure** (2026-11-17, dataset UCI 697,
entorno ya eliminado) y lo **validado en local con ENAPE 2021** (2026-11-18).

Estados:

- **Cumple** — implementado, ejecutado y con evidencia.
- **Parcial** — implementado y probado, con una desviación justificada.
- **Pendiente** — requiere una acción externa (credenciales, cuota, decisión) o
  el relanzamiento del 19-11.

Evidencia viva: `docs/dashboard.html` (panel generado con datos reales),
`docs/demo-curl-azure.md` (pruebas del endpoint) y `docs/despliegue-azure.md`
(runbook y checklist).

## Rúbrica del brief

| Criterio | Peso | Estado |
|---|---|---|
| Infraestructura Azure con Terraform | 20 % | Cumple |
| Pipeline de entrenamiento con MLflow tracking | 20 % | Cumple |
| Model Registry con criterio de promoción | 15 % | Cumple (gate ENAPE superado en local) |
| Endpoint de inferencia funcional en ACI | 20 % | Cumple |
| Pipeline CI/CD MLOps completo | 15 % | Pendiente |
| Monitoreo, documentación y análisis de costos | 10 % | Cumple |

## Infraestructura Azure con Terraform (20 %)

| Requisito | Implementación | Estado |
|---|---|---|
| Resource Group, Azure ML Workspace, Storage, Key Vault, ACR | `terraform/main.tf`; 27 recursos en el state remoto de `rg-mlopslab-dev` (corrida 17-11; state vacío tras el destroy del 18-11) | Cumple |
| Compute cluster `Standard_DS3_v2`, min 0 / max 4 | `terraform/training.tf`; desplegado **min 0 / max 2** por cuota `standardDSv3Family` (10 vCPU, 4 por nodo) | Parcial |
| ACI 1 vCPU / 1.5 GB con imagen desde ACR | `terraform/inference.tf`; `aci-mlopslab-dev-inference` sirvió `acrmlopslabdev.azurecr.io/endpoint:v2`; en el relanzamiento será `v3` | Cumple |
| Log Analytics para centralizar logs | `log-mlopslab-dev`, diagnóstico del ACI a `ContainerInstanceLog_CL` | Cumple |
| Terraform desplegado y funcional | `terraform plan` sin cambios el 17-11; `fmt -check` y `validate` en verde el 18-11; state con versionado de blobs | Cumple |

## Pipeline de entrenamiento con MLflow tracking (20 %)

| Requisito | Implementación | Estado |
|---|---|---|
| Dataset tabular de clasificación | **ENAPE 2021** (INEGI): 32.343 × 67 crudo → cohorte de 18.207 estudiantes × 18 variables, 6,48 % de abandono; Data Asset `enape-abandono` | Cumple en local; registro en Azure al relanzar |
| Ingesta con Azure Data Factory | `adf-mlopslab-dev`: linked service, 3 datasets, Data Flow `df_clean_enape` y pipeline `pl_clean_enape`; corrida `Succeeded` con el pipeline UCI el 17-11 | Cumple (ENAPE definido en Terraform) |
| Entrenamiento scikit-learn como Azure ML Job | Job `mighty_nut_8jvyq81p06` en `Completed` sobre `cpu-cluster` el 17-11; el job actual apunta a `enape-training` (`ml/pipeline/train.py`) | Cumple (ENAPE validado en local) |
| MLflow: parámetros, métricas y artefactos | `mlflow.sklearn.autolog` + métricas por clase, ROC-AUC, PR-AUC, matriz de confusión, importancia y perfil de drift en el run | Cumple |
| Reproducibilidad del entorno | Environment versionado con imagen propia en ACR | Cumple |
| Informe con ≥ 5 runs de hiperparámetros | 36 runs de tuning en `mlruns/` local (`docs/experimentos-mlflow.md`, con UCI 697); en Azure sólo el run final | Parcial |

## Model Registry con criterio de promoción (15 %)

| Requisito | Implementación | Estado |
|---|---|---|
| Registro del modelo en el workspace | `enape-abandono` (el histórico `dropout-classifier` v1 se conserva como evidencia) | Cumple en local; registro en Azure al relanzar |
| Gate de promoción | `ml/pipeline/evaluate.py`: **PR-AUC ≥ 0.35**, **recall de `Abandona` ≥ 0.60**, sin retroceso de PR-AUC frente a Production y versión distinta; probado en local con ENAPE (aprobado) | Cumple |
| Promoción Staging → Production | `ml/pipeline/promote.py` con smoke test previo; no ejecutada contra Azure todavía | Pendiente (se ejecuta tras el `verify` del 19-11) |

Métricas del candidato ENAPE (test estratificado 20 %, 3.642 estudiantes):
ROC-AUC **0.862**, PR-AUC **0.404**, exactitud **0.858**, F1 macro **0.656**.
Por clase: `Continua` P 0.978 / R 0.868 / F1 0.919 (3.406 casos) y `Abandona`
P 0.272 / R 0.712 / F1 0.393 (236 casos). El gate lo marca elegible.

Métricas históricas del modelo UCI 697 registrado: accuracy **0.7571**, F1 macro
**0.7002** (Dropout 0.761, Enrolled 0.481, Graduate 0.859). Se conservan en
`docs/despliegue-azure.md` como evidencia de la corrida del 17-11.

## Endpoint de inferencia en ACI (20 %)

| Requisito | Implementación | Estado |
|---|---|---|
| Imagen Docker del endpoint en ACR | `endpoint:v1` y `endpoint:v2` (v2 añade CORS para el panel); el relanzamiento publica **`v3`** con el modelo ENAPE | Cumple |
| ACI con 1 vCPU / 1.5 GB y API key | Terraform inyecta `API_KEY` desde Key Vault como variable segura | Cumple |
| `/predict` con JSON | Devuelve clase (`Continua`/`Abandona`), probabilidades, `dropout_risk` y `risk_level`; también `/predict/batch`, `/explain`, `/feedback`, `/model-info` | Cumple |
| Verificación funcional | `/health` 200, `/predict` 401 sin key, predicción con key y `/feedback` 202 (4/4 el 17-11); se repite con ENAPE el 19-11 | Cumple |
| Costo controlado fuera de la demo | ACI detenido (`stop`) y, tras la entrega, `destroy` completo | Cumple |

URL de la corrida 17-11 (ya eliminada):
`http://mlops-mlopslab-dev.centralus.azurecontainer.io:8000`; Swagger en `/docs`.

## Pipeline CI/CD MLOps (15 %)

| Stage exigido | Implementación en `.azure-pipelines/azure-pipelines.yml` | Estado |
|---|---|---|
| `data-prep` | `validate.py`, subida a Blob y `run_adf_pipeline.sh` | Listo, sin ejecutar |
| `train` | `az ml job create` + polling de estado + descarga de métricas | Listo, sin ejecutar |
| `evaluate` | `evaluate.py` y salida `deploy` para el stage siguiente | Listo, sin ejecutar |
| `deploy` | build/push a ACR, `terraform apply -target` del ACI, smoke test y promoción | Listo, sin ejecutar |

**Bloqueo:** el proyecto de Azure DevOps no tiene service connection ARM con
Workload Identity Federation ni variable group vinculado a Key Vault. Todo el
YAML, los scripts y el environment con aprobación manual están escritos y
versionados; falta el objeto de Azure AD/DevOps que sólo puede crear un
administrador del tenant.

## Monitoreo, documentación y costos (10 %)

| Requisito | Implementación | Estado |
|---|---|---|
| Data drift | `ml/monitoring/drift.py` (PSI + KS), baseline y choque simulado probados; `drift-monitoring.yml` diario | Cumple en local; programación pendiente en DevOps |
| Accuracy decay | `ml/monitoring/performance.py` cruza `/feedback` con predicciones por `prediction_id` | Cumple |
| Latencia P99 y errores | `alert-mlopslab-dev-latency-p99` y `-endpoint-errors` (scheduled query rules) | Cumple |
| Salud del contenedor | `alert-mlopslab-dev-aci-cpu` + action group con correo | Cumple |
| Cuadro de mando | Workbook de Azure Monitor: volumen, riesgo, latencia y accuracy | Cumple |
| Documentación | `README.md`, `docs/guia-tecnica.md`, `docs/despliegue-azure.md`, `docs/costos.md`, `docs/experimentos-mlflow.md`, `terraform/README.md` | Cumple |
| Análisis de costos | `docs/costos.md`: DS3_v2 vs NC4as_T4_v3/NC6s_v3 y costo por 1 000 predicciones | Cumple |
| Panel de pruebas | `docs/dashboard.html` + `scripts/build_dashboard.ps1` | Cumple |

## Servicios de Azure empleados

| Servicio | Uso en el proyecto |
|---|---|
| Azure Machine Learning (workspace, compute cluster, jobs, environments, Model Registry, Data Assets) | Entrenamiento, tracking, registro y linaje |
| Azure Data Factory (linked services, datasets, Data Flow, pipeline) | Ingesta y limpieza del dataset |
| Azure Storage (Blob) | Dataset crudo/procesado, artefactos y state de Terraform |
| Azure Container Registry | Imágenes del endpoint y del environment |
| Azure Container Instances | Inferencia en producción |
| Azure Key Vault | `endpoint-api-key` y secretos del pipeline |
| Log Analytics | Logs del contenedor y base de las consultas de alerta |
| Application Insights | Telemetría del endpoint |
| Azure Monitor (metric alerts, scheduled query rules, action group, workbook) | Monitoreo y cuadro de mando |
| Managed Identities + RBAC (`AcrPush`, `AcrPull`, Storage Blob Data Contributor) | Autenticación sin secretos entre servicios |
| Azure DevOps (YAML, environments, variable groups) | CI/CD definido, pendiente de service connection |

Elegibles pero **no** usados, con motivo:

- **GPU (`NC4as_T4_v3`, `NC6s_v3`)**: el brief fija `Standard_DS3_v2` y el
  modelo es un RandomForest sobre 18.207 filas y 16 variables; la GPU no cambia
  el resultado y multiplica el costo. Comparado en `docs/costos.md`.
- **AKS / Azure ML managed online endpoints**: el brief exige ACI para la
  inferencia; se documentan como evolución natural.
- **VNet + private endpoints + HTTPS**: no lo pide el brief y añade costo fijo;
  queda anotado como mejora.
- **Event Hubs / IoT Hub / Synapse**: no aplican al caso de uso académico.

## Brechas antes de la entrega final

1. **Relanzar con ENAPE**: `-Stage all -ImageTag v3` (data → train → image →
   aci → verify → stop). Es lo único que separa el repo del estado "desplegado".
2. **Cuota de cómputo**: `compute_max_nodes = 4` exige ampliar la cuota
   `standardDSv3Family`; hoy está en 2 nodos.
3. **Azure DevOps**: crear service connection ARM (WIF), variable group y
   environment con aprobación; registrar `azure-pipelines.yml` y
   `drift-monitoring.yml`.
4. **Promoción a Production**: el gate ENAPE ya está superado en local; falta
   ejecutar `promote.py` contra el workspace.
5. **≥ 5 runs de MLflow en Azure**: los 36 runs están en local; se pueden subir
   lanzando el job de tuning.
6. **Evidencia visual**: capturas del portal y del pipeline verde para el
   informe; el panel `docs/dashboard.html` cubre el resto con datos reales.
