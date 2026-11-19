# Despliegue en Azure — guía por etapas

Runbook para llevar el proyecto de "validado en local" a "corriendo en Azure"
sin crear recursos por accidente. **Cada etapa se lanza a mano**; el script
`scripts/azure_up.ps1` no encadena nada salvo que se use `-Stage all`.

> Para el detalle de *qué archivo de Terraform* hace cada cosa y *dónde mirar en
> el portal*, ver **`docs/guia-tecnica.md`**. Este documento es el runbook
> operativo; aquel es el mapa técnico.

- Estado del repo: dataset **ENAPE 2021** generado y validado, modelo
  `enape-abandono` entrenado en local (ROC-AUC 0.862 / PR-AUC 0.404 / recall de
  `Abandona` 0.712), **52/52 pruebas** en verde y `terraform validate` sin
  errores.
- La infraestructura se aplicó el **2026-11-17** en la suscripción
  `Azure subscription 1` (27 recursos en `rg-mlopslab-dev`, state en
  `rg-tfstate-mlops`) y se **eliminó por completo el 2026-11-18** para no
  consumir crédito. `terraform state list` quedó vacío y sólo sobrevive
  `rg-tfstate-mlops`.
- El relanzamiento con ENAPE (`-Stage all -ImageTag v3`) está previsto para el
  **2026-11-19**: presupuesto ≈ **0,2–0,35 USD**.
- Costo con el entorno encendido solo durante la demo: ver `docs/costos.md`.
  La suscripción es Azure for Students (USD 100/año).

## 1. Requisitos previos

| Herramienta | Uso | Verificación |
|---|---|---|
| Azure CLI ≥ 2.60 | crear todo y ejecutar ADF / jobs | `az version` |
| Terraform ≥ 1.5 (probado con 1.17.1) | infraestructura | `terraform version` |
| Docker Desktop | construir y publicar la imagen | `docker info` |
| Git Bash | scripts `.sh` de datos y descarga del modelo | `bash --version` |
| PowerShell 5.1 o 7 | script de despliegue | `$PSVersionTable` |

Inicia sesión y elige la suscripción correcta:

```powershell
az login
az account show --query "{name:name,id:id,tenant:tenantId}" -o table
# Si tienes varias:
az account set --subscription "<id o nombre>"
```

### Caché de providers fuera de OneDrive (obligatorio en este equipo)

Si el repo vive dentro de una carpeta sincronizada por OneDrive, un antivirus de
terceros (aquí *Reason Cybersecurity*) puede marcar el provider `azurerm.exe` de
238 MB al escribirlo y `terraform init` falla con:

```text
Error while installing hashicorp/azurerm v3.117.1: open .terraform\providers\...
Operation did not complete successfully because the file contains a virus
or potentially unwanted software.
```

La solución —sin desactivar el antivirus ni tocar permisos— es dejar los
binarios fuera de OneDrive y reutilizarlos con la caché de plugins:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\<usuario>\tf-plugin-cache | Out-Null
$env:TF_PLUGIN_CACHE_DIR = "C:\Users\<usuario>\tf-plugin-cache"
```

Define esa variable **antes** de ejecutar `scripts/azure_up.ps1`. Con la caché,
Terraform usa los providers desde fuera del repo y `.terraform/providers` queda
vacío a propósito. Si algún día el `init` vuelve a fallar, borra
`terraform\.terraform` (`cmd /c rd /s /q`) y repite.

Comprueba que la suscripción permite crear recursos en `centralus`
(`eastus` está bloqueado en esta cuenta):

```powershell
az provider register -n Microsoft.MachineLearningServices
az vm list-usage -l centralus --query "[?name.value=='standardDSv3Family'].{usado:currentValue,limite:limit}" -o table
```

Si el límite de `standardDSv3Family` es `0`, baja `compute_max_nodes = 1` en
`terraform/terraform.tfvars` (o pide cuota) antes de la etapa `base`.

## 2. Nombres y convenciones

Los nombres derivan de `project_name` y `environment` y deben coincidir en
Terraform, los pipelines y el script:

> `project_name = "mlopslab"` (no `mlopsproj`): el nombre de ACR es global y
> `acrmlopsprojdev` ya estaba tomado por otra suscripción. El prefijo corto se
> usa también en el pipeline de Azure DevOps y en el backend del state.

| Recurso | Nombre |
|---|---|
| Resource group | `rg-mlopslab-dev` |
| ML Workspace | `mlw-mlopslab-dev` |
| Storage de datos | `stmlopslabdev001` |
| ACR | `acrmlopslabdev` (`acrmlopslabdev.azurecr.io`) |
| Key Vault | `kv-mlopslab-dev` (secreto `endpoint-api-key`) |
| Data Factory | `adf-mlopslab-dev` (`pl_clean_enape` / `df_clean_enape`) |
| Log Analytics / App Insights | `log-mlopslab-dev` / `appi-mlopslab-dev` |
| Compute cluster | `cpu-cluster` (`Standard_DS3_v2`, 0–2 nodos) |
| ACI | `aci-mlopslab-dev-inference` |
| State | `rg-tfstate-mlops` / `sttfstatemlopslab` / `tfstate` / `mlopslab-dev.tfstate` |

Configuración local (no se versiona):

```powershell
cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars
# edita alert_emails y, si aplica, compute_max_nodes / compute_vm_priority
```

`terraform.tfvars` y `terraform/backend.hcl` están en `.gitignore`. El script
crea `backend.hcl` automáticamente si falta.

## 3. Etapas del despliegue

Todas se ejecutan desde la raíz del repo. El parámetro `-ImageTag` es el tag que
se publica en ACR y se pone en el ACI (para esta entrega: `v3`).

### Etapa 0 — Preflight (sin crear nada)

```powershell
.\scripts\azure_up.ps1 -Stage preflight
```

Comprueba `az`/`terraform`, que haya sesión de Azure, que Docker esté vivo (si
la etapa lo necesita), imprime los nombres que usará y avisa si el resource
group ya existe o si la cuota de DSv3 es 0. **No crea recursos.**

### Etapa 1 — Estado remoto de Terraform

```powershell
.\scripts\azure_up.ps1 -Stage state
```

Crea el resource group del state, la cuenta de almacenamiento con versionado de
blobs, el contenedor `tfstate` y asigna `Storage Blob Data Contributor` al
usuario que ejecuta. Además genera `terraform/backend.hcl`.

Verifica:

```powershell
az storage container list --account-name sttfstatemlopslab --auth-mode login -o table
```

> Si el state ya existía de una sesión anterior, la etapa es idempotente. Tras el
> `destroy` del 18-11 el state está **vacío**, así que el `apply` vuelve a crear
> los 27 recursos desde cero.

### Etapa 2 — Infraestructura base (sin ACI)

```powershell
.\scripts\azure_up.ps1 -Stage base
```

Hace `terraform init`, `validate`, `plan` y `apply`. Crea Storage, Key Vault,
ACR, Log Analytics, App Insights, workspace de Azure ML, compute cluster,
datastores, Data Factory (pipeline + Data Flow), RBAC y alertas. Deja el ACI
apagado (`deploy_aci = false`).

> El workspace de Azure ML necesita `AcrPush` sobre el ACR para publicar las
> imágenes de environment que construyen los jobs. Terraform crea ese permiso
> (más `AcrPull`) en `main.tf`; si se omite, el primer job se queda en
> `Preparing` sin error visible y el clúster nunca escala.

Antes de aplicar comprueba que el state esté vacío si el RG ya existe; el script
aborta para no duplicar recursos (usa `-Force` solo si ya importaste).

Al terminar revisa:

```powershell
cd terraform; terraform output; cd ..
az ml workspace show -n mlw-mlopslab-dev -g rg-mlopslab-dev --query "{name:name,location:location}" -o table
```

### Etapa 3 — Datos (Blob → Data Factory → Data Asset)

```powershell
.\scripts\azure_up.ps1 -Stage data
```

Sube `ml/data/enape.csv` a `raw/enape/latest/` (más una copia versionada
`raw/enape/<yyyyMMddHHmm>/`), ejecuta el pipeline `pl_clean_enape` (Data Flow
`df_clean_enape`), espera a que termine, deja las filas rechazadas en
`raw/rejected/enape/rejected.csv` y registra el Data Asset **`enape-abandono`**
con versión `yyyyMMddHHmm` apuntando a
`azureml://datastores/processed_data/paths/enape/<versión>/enape.csv`.

Qué hace el Data Flow (`terraform/dataflows/clean_enape.dfs`):

| Transformación | Regla |
|---|---|
| `SplitRows` | rechaza nulos, `inscrito != 1`, edad fuera de 6–100, `inscrito_actual ∉ {1,2}`, `nins_causa == 4` y binarias fuera de {1,2} |
| `DeriveFeatures` | renombra al contrato, recodifica 1/2 → 1/0, deriva `abandono` y `abandono_label` |
| `SelectFeatures` | deja `FOLIO` + 18 variables + etiqueta |
| `DistinctRows` + `DropHash` | deduplica por hash de todas las columnas |

> El Data Flow levanta un cluster Spark: la primera corrida puede tardar 8–15
> min. Si falla por permisos, espera unos minutos (propagación de RBAC de la
> identidad de ADF) y reintenta.

Verifica:

```powershell
az storage blob list --account-name stmlopslabdev001 --container-name processed --auth-mode login -o table
az ml data list --workspace-name mlw-mlopslab-dev -g rg-mlopslab-dev -o table
```

### Etapa 4 — Entrenamiento en Azure ML

```powershell
.\scripts\azure_up.ps1 -Stage train
```

Instala la extensión `ml`, crea el job de `ml/pipeline/job.yaml` (experimento
`enape-training`) con el Data Asset `enape-abandono@latest`, consulta el estado
por polling hasta `Completed` (máximo 120 min) y descarga las métricas a
`outputs/azure/`. El job registra **`enape-abandono`** en **Staging**; no
promueve.

> Se usa polling con `az ml job show` en lugar de `az ml job stream`: con la
> extensión `ml` 2.45.2 el stream aborta con
> `ERROR: Met error <class 'binascii.Error'>:Incorrect padding` aunque el job
> siga corriendo.

La primera ejecución tarda 10–15 min: el clúster está en 0 nodos y Azure ML
aprovisiona la VM `Standard_DS3_v2` antes de arrancar el contenedor. `.amlignore`
excluye entornos virtuales, CSV derivados, cachés y salidas locales, y conserva
las fuentes y definiciones necesarias para que el job sea reproducible.

Verifica en Azure ML Studio (Jobs → `enape-training`) o:

```powershell
az ml job list --workspace-name mlw-mlopslab-dev -g rg-mlopslab-dev --query "[0].{name:name,status:status}" -o table
az ml model list --name enape-abandono --workspace-name mlw-mlopslab-dev -g rg-mlopslab-dev -o table
```

El gate (`ml/pipeline/evaluate.py`) se ejecuta en el pipeline de Azure DevOps
(`Evaluate`) y también en local:

| Regla | Umbral |
|---|---|
| PR-AUC | ≥ 0.35 |
| Recall de `Abandona` | ≥ 0.60 |
| Regresión de PR-AUC vs Production | ≤ 0.005 |
| Misma versión que Production | prohibido |

Para promover la versión aprobada:

```powershell
$env:MLFLOW_TRACKING_URI = az ml workspace show -n mlw-mlopslab-dev -g rg-mlopslab-dev `
  --query mlflow_tracking_uri -o tsv
python -m ml.pipeline.promote --version <n>   # requiere azureml-mlflow instalado
```

Si aún no hay versión en Production, la etapa `image` descarga la más reciente
y el ACI arranca con ella; promueve después del `verify` para que Production
coincida con lo que sirve el endpoint.

### Etapa 5 — Imagen Docker → ACR

```powershell
.\scripts\azure_up.ps1 -Stage image -ImageTag v3
```

Descarga la versión en Production del Model Registry (`download_model.sh`;
si no hay ninguna, la más reciente), verifica que exista `MLmodel` en
`endpoint/model/enape-abandono/`, hace `az acr login`, construye
`acrmlopslabdev.azurecr.io/endpoint:v3` (y `:latest`) y las publica.

Si quieres usar el modelo ya exportado en local, agrega `-UseLocalModel` (el
paquete lo genera `scripts/export_local_model.py`, que lee
`outputs/model/model.pkl` y escribe el artefacto MLflow con el mismo formato).

Verifica:

```powershell
az acr repository show-tags -n acrmlopslabdev --repository endpoint -o table
```

> ACR Tasks está bloqueado en la suscripción educativa; por eso se construye
> con Docker local o en el agente de Azure Pipelines.

### Etapa 6 — ACI (Terraform es el dueño)

```powershell
.\scripts\azure_up.ps1 -Stage aci -ImageTag v3
```

Hace `terraform apply -target=azurerm_container_group.inference` con
`deploy_aci=true` y `endpoint_image_tag=v3`. El ACI arranca con identidad
administrada, `X-API-Key` desde Key Vault, liveness probe y diagnóstico a Log
Analytics. Imprime la URL del endpoint.

**No uses `az container create`**: un PUT de la CLI borra identidad, probe y
diagnóstico. El stage `Deploy` del pipeline también aplica Terraform por eso.

Verifica:

```powershell
az container show -n aci-mlopslab-dev-inference -g rg-mlopslab-dev `
  --query "{state:instanceView.state,fqdn:ipAddress.fqdn,image:containers[0].image}" -o table
```

### Etapa 7 — Verificación funcional

```powershell
.\scripts\azure_up.ps1 -Stage verify
```

Espera a `/health`, lee `endpoint-api-key` de Key Vault y prueba:

- `GET /health` → `200` con `model_loaded: true` y `model_version`.
- `POST /predict` sin `X-API-Key` → `401`.
- `POST /predict` con key → `prediction`, `probabilities`, `dropout_risk`,
  `risk_level` y `prediction_id`.
- `POST /feedback` → `202`.

El payload sale de `endpoint/examples/` (18 variables ENAPE). La evidencia se
escribe en `docs/demo-curl-azure.md`, lista para el informe.

### Panel de pruebas (dashboard)

```powershell
pwsh -File scripts/build_dashboard.ps1          # corre pytest y lee Azure CLI
pwsh -File scripts/build_dashboard.ps1 -SkipTests
```

Genera `docs/dashboard.html` autocontenido (sin CDN ni servidor web): ábrelo en
el navegador. Tema oscuro, sin datos de la cuenta ni de la suscripción. Incluye
el conjunto de datos ENAPE (filas, cohorte, distribución de clases), las
métricas del modelo, la verificación del endpoint, el job, el inventario de
recursos y el estado del entorno. Si el ACI está detenido o el RG se eliminó, el
panel lo indica y muestra los comandos para volver a levantarlo.

### Etapa 8 — Azure DevOps (CI/CD)

En el proyecto de Azure DevOps:

1. **Service connection** ARM `sc-azure-mlops` con Workload Identity
   Federation:
   - `Contributor` sobre `rg-mlopslab-dev`.
   - `Storage Blob Data Contributor` sobre `stmlopslabdev001` y
     `sttfstatemlopslab` (el pipeline hace `terraform init` contra el state).
2. **Variable group** `mlops-dev` vinculado a `kv-mlopslab-dev` con:
   - `endpoint-api-key` (secreto generado por Terraform).
   - `azureSubscription = sc-azure-mlops`, `resourceGroup`, `project`,
     `environment` si no se sobrescriben en el YAML.
   - La identidad del proyecto necesita `Key Vault Secrets User` en el vault.
3. **Environment** `production` con aprobación manual (gate antes del ACI).
4. **Pipelines**: `/.azure-pipelines/azure-pipelines.yml` y
   `/.azure-pipelines/drift-monitoring.yml` (este último con schedule diario).
5. Ejecuta el pipeline principal una vez con la rama que contiene los cambios.
   Etapas: CI → DataPrep → Train → Evaluate → Build & Push → Deploy (aprobación)
   → smoke test → promoción a Production.

## 4. Apagar y limpiar

```powershell
.\scripts\azure_up.ps1 -Stage stop     # az container stop: conserva el ACI y el state
.\scripts\azure_up.ps1 -Stage destroy  # terraform destroy; pide escribir "destroy"
```

- `stop` es lo que ahorra crédito: ACI cobra por segundo encendido.
- `destroy` elimina los recursos del proyecto, pero **conserva** la cuenta del
  state. Purga el Key Vault soft-deleted para que el mismo nombre se pueda
  reutilizar de inmediato (en dev no tiene purge protection); si la purga falla:
  `az keyvault purge -n kv-mlopslab-dev -l centralus`.
  Para borrar el state: `az group delete -n rg-tfstate-mlops --yes`.
- `terraform destroy` debe ejecutarse con `deploy_aci=true` (lo hace el script)
  para que el ACI esté en el state y se elimine.
- Si `destroy` falla con **`deleting Resource Group ... the Resource Group still
  contains Resources`**, el culpable es el action group *Application Insights
  Smart Detection*, que crea Application Insights por su cuenta y Terraform no
  gestiona. Ya está resuelto en `terraform/providers.tf`
  (`prevent_deletion_if_contains_resources = false`); si el state es anterior a
  ese cambio, el script borra el RG con `az group delete` y reintenta solo.
- Tras un `destroy` fallido, comprueba el state con `terraform state list`: debe
  quedar vacío. Un `terraform destroy` adicional elimina la referencia al RG
  que ya no existe.

### Limpieza ejecutada el 2026-11-18

```text
terraform destroy  → 32 de 33 objetos
az group delete    → rg-mlopslab-dev (action group Smart Detection)
az keyvault purge  → kv-mlopslab-dev
terraform state list → vacío
az group list      → rg-tfstate-mlops, rg-tfstate-examen
```

Queda **cero cómputo y cero ACR**: no hay gasto mientras no se relance.

## 5. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `No hay sesión de Azure` | Ejecuta `az login` y repite la etapa. |
| `terraform init` falla con "Operation did not complete successfully because the file contains a virus" | Antivirus de terceros marcando el provider dentro de OneDrive; define `TF_PLUGIN_CACHE_DIR` fuera de OneDrive y borra `terraform\.terraform` (ver §1). |
| `terraform init`: `No positional arguments are expected` | PowerShell 7.7 parte argumentos como `-backend-config=backend.hcl`. Usa la forma con espacio (`-backend-config backend.hcl`); el script ya lo hace. |
| `az ml job stream`: `binascii.Error: Incorrect padding` | Bug de la extensión `ml`; el job sigue vivo. Consulta con `az ml job show -n <job> --query status`; el script ya hace polling. |
| Data Flow falla con `DFExecutorUserError` … `blob storage kind is Storage (general purpose v1)` | El linked service `ls_storage` sin `storage_kind`: Data Flow asume v1 y rechaza la identidad administrada. Debe ser `storage_kind = "StorageV2"` (`datafactory.tf`). |
| El job se queda en `Preparing` y `cpu-cluster` sigue con 0 nodos | Falta `AcrPush` para el MSI del workspace en el ACR: Azure ML no puede publicar la imagen del environment y no reporta error. Verifica con `az role assignment list --scope <acr-id>`; Terraform lo crea en `main.tf`. Tras concederlo, cancela el job y relánzalo. |
| Docker Desktop no está corriendo | Abre Docker Desktop y espera `Engine running`; `docker info` debe responder. |
| Cuota `standardDSv3Family` en 0 | Baja `compute_max_nodes = 1` o pide cuota; el cluster no creará nodos. |
| El RG existe y el state está vacío | Importa los recursos existentes (ver `terraform/README.md`) o usa otro `project_name`; el script aborta a propósito. |
| Data Flow falla con `403` | Propagación de RBAC de la identidad de ADF; espera 5–15 min y reintenta. |
| `az ml job create` falla por el Data Asset | La etapa `data` no terminó: confirma `azureml:enape-abandono@latest` en Azure ML. |
| El ACI no responde `/health` | Revisa `az container logs -n aci-mlopslab-dev-inference -g rg-mlopslab-dev`; normalmente es la API key o la imagen. |
| `/health` devuelve `model_version: null` | La imagen se construyó sin `registered_model_meta`: reconstruye con `-Stage image` (el script lo escribe al descargar el modelo). |
| `terraform apply` quiere destruir el ACI | `deploy_aci` volvió a `false`: usa `-var="deploy_aci=true"` en todos los applies posteriores. |
| `destroy` falla: `the Resource Group still contains Resources` | Application Insights crea el action group `Application Insights Smart Detection`; ya resuelto con `prevent_deletion_if_contains_resources = false` en `providers.tf`. |

## 6. Checklist de aceptación

Corrida histórica con UCI 697 (2026-11-17), ya eliminada:

- [x] `preflight` sin errores y con la suscripción correcta.
- [x] `state` con versionado de blobs y `backend.hcl` generado.
- [x] `base` aplicado; 27 recursos y `terraform plan` sin cambios.
- [x] `data` con ADF `Succeeded` y Data Asset `student-dropout:202611171707`.
- [x] `train` en `Completed` (job `mighty_nut_8jvyq81p06`, accuracy 0.7571).
- [x] `image` publica `endpoint:v1` y `endpoint:v2`.
- [x] `aci` en `Running` (`mlops-mlopslab-dev.centralus.azurecontainer.io`).
- [x] `verify`: `/health` 200, `/predict` 401 sin key, predicción con key y
      `/feedback` 202; evidencia en `docs/demo-curl-azure.md`.
- [x] Alertas, action group y workbook desplegados.

Corrida ENAPE (2026-11-19), a completar al relanzar:

- [ ] `data` deja `processed/enape/latest/enape.csv` y `enape-abandono:<versión>`.
- [ ] `train` en `Completed` sobre `enape-training` y `enape-abandono` v1 en Staging.
- [ ] Gate: PR-AUC ≥ 0.35 y recall de `Abandona` ≥ 0.60.
- [ ] `image` publica `endpoint:v3` (y `latest`).
- [ ] `aci` en `Running` con la imagen `v3`.
- [ ] `verify` con los 4 checks en verde y evidencia nueva en `docs/demo-curl-azure.md`.
- [ ] `stop` ejecutado al terminar; `docs/dashboard.html` regenerado.

Pendiente estructural:

- [ ] Pipeline de Azure DevOps verde y `drift-monitoring.yml` programado
      (falta service connection ARM y variable group).

## 7. Qué queda demostrado y qué no

**Demostrado en local (2026-11-18):** preparación y validación del dataset ENAPE
2021 (18.207 filas, 6,48 % positivos, 127 duplicados), entrenamiento real del
modelo (ROC-AUC 0.862 / PR-AUC 0.404 / recall de `Abandona` 0.712), gate
superado, exportación del modelo a formato MLflow, regeneración de los 18
payloads de ejemplo y **52 pruebas** de `ml/` + `endpoint/` en verde.
`terraform fmt -check` y `terraform validate` sin errores.

**Demostrado en Azure (2026-11-17, UCI 697):** 27 recursos gestionados por
Terraform, Data Flow real, job en `Completed` sobre `cpu-cluster`,
`dropout-classifier` v1 en el Model Registry, imágenes `endpoint:v1`/`v2` en
ACR, ACI sirviendo `/health`, `/predict` y `/feedback`, más alertas, action group
y workbook sobre Log Analytics. El entorno se eliminó el 18-11.

**Pendiente de demostrar:**
- La corrida ENAPE completa en Azure (`-Stage all -ImageTag v3`): datos → train
  → imagen → ACI → verify → stop.
- Pipeline de Azure DevOps de punta a punta (falta service connection ARM por
  Workload Identity Federation y variable group en el proyecto).
- `drift-monitoring.yml` programado (mismo bloqueo).
- ≥ 5 runs de MLflow en el workspace de Azure: los runs de tuning viven en
  `mlruns/` local; se pueden subir lanzando un job de tuning.
- Compute `max_nodes = 4`: desplegado con 2 por cuota `standardDSv3Family`
  (10 vCPU) de la suscripción.
