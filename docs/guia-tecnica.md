# Guía técnica — qué hace cada pieza y dónde encontrarla

Este documento explica, etapa por etapa, **qué se ejecuta, qué se crea en Azure y
en qué archivo vive cada decisión**. Está pensado para responder tres preguntas
concretas:

1. ¿Qué comando lanzo y qué espero que pase?
2. ¿Dónde está eso en el código (Terraform, Python, YAML)?
3. ¿Dónde lo veo en el portal de Azure si algo falla?

El runbook operativo con las cifras de cada corrida está en
`docs/despliegue-azure.md`, la evidencia cruda del endpoint en
`docs/demo-curl-azure.md` y el resumen visual en `docs/dashboard.html`. Para la
sustentación, **`docs/preguntas-defensa.md`** reúne las preguntas probables del
profesor (Terraform, Azure, ML y operación) con las decisiones y su porqué.

> **Estado al 2026-11-18.** El entorno de la corrida del 17-11 se eliminó por
> completo para no consumir crédito (`terraform state list` vacío, RG inexistente).
> El dataset se migró a **ENAPE 2021** y el pipeline se validó en local ese mismo
> día; el despliegue en Azure se relanza con `-Stage all -ImageTag v3`.

---

## 1. Mapa del repositorio

```text
Proyecto-Azure-MLops/
├── archive (1)/                  # ENAPE 2021 crudo (INEGI)
│   └── df03_Dataset_ENAPE.csv    # 32.343 filas × 67 columnas
│
├── terraform/                    # toda la infraestructura (nada se crea a mano)
│   ├── providers.tf              # versiones del provider + backend remoto
│   ├── variables.tf              # 15 variables, con defaults pensados para dev
│   ├── terraform.tfvars          # valores reales (no se versiona)
│   ├── main.tf                   # RG, Storage, Key Vault, ACR, logs, Azure ML
│   ├── training.tf               # compute cluster + datastores del workspace
│   ├── datafactory.tf            # ADF: linked service, 3 datasets, data flow, pipeline
│   ├── dataflows/clean_enape.dfs # el script real del Data Flow
│   ├── inference.tf              # ACI, secreto de API key, RBAC, alertas
│   ├── monitoring.tf             # alerta de latencia + workbook
│   └── outputs.tf                # lo que consumen los scripts
│
├── ml/
│   ├── data/
│   │   ├── load_enape.py         # cohorte + etiqueta + contrato de 18 variables
│   │   ├── load_data.py          # loader UCI 697 anterior (legado, no se usa)
│   │   ├── validate.py           # contrato del dataset (tipos, rangos, clases)
│   │   ├── upload_to_blob.sh     # etapa data (1/2): sube a raw/
│   │   └── run_adf_pipeline.sh   # etapa data (2/2): ADF + Data Asset
│   ├── pipeline/
│   │   ├── modeling.py           # FEATURES, MODEL_FEATURES, TARGET, CLASSES
│   │   ├── train.py              # entrena, loguea en MLflow, registra el modelo
│   │   ├── evaluate.py           # gate (PR-AUC y recall) contra Production
│   │   ├── promote.py            # mueve la versión a Production
│   │   ├── job.yaml              # definición del job de Azure ML
│   │   └── reporting.py          # gráficas de métricas
│   ├── monitoring/
│   │   ├── drift.py              # data drift (PSI + KS) contra el perfil de referencia
│   │   └── performance.py        # accuracy observada a partir de /feedback
│   └── tests/                    # 52 pruebas de pytest
│
├── endpoint/
│   ├── app.py                    # FastAPI: /health, /predict, /feedback, /explain
│   ├── Dockerfile                # imagen que se publica en ACR
│   ├── examples/                 # payloads listos para curl (18 variables)
│   └── model/enape-abandono/     # modelo empaquetado que se hornea en la imagen
│
├── scripts/
│   ├── azure_up.ps1              # orquestador por etapas (preflight → destroy)
│   ├── snapshot_azure.ps1        # congela el estado de Azure en un JSON
│   ├── build_dashboard.ps1       # genera docs/dashboard.html
│   ├── export_local_model.py     # empaqueta el modelo local como artefacto MLflow
│   ├── export_production_model.py# baja el modelo de Production del registry
│   └── make_examples.py          # regenera endpoint/examples/*.json
│
├── .azure-pipelines/
│   ├── azure-pipelines.yml       # CI → DataPrep → Train → Evaluate → Build → Deploy
│   └── drift-monitoring.yml      # monitoreo programado
│
└── docs/                         # runbook, evidencia, costos, este documento
```

Regla de oro del repo: **Terraform es el único dueño de los recursos**. Los
scripts PowerShell y Bash sólo llaman a Terraform o a `az` para operaciones que
no cambian la forma del recurso (subir un blob, lanzar un pipeline, leer un
secreto).

---

## 2. El dataset: ENAPE 2021

La fuente es la **Encuesta Nacional de Acceso y Permanencia en la Educación
(ENAPE) 2021** del INEGI. El archivo `archive (1)/df03_Dataset_ENAPE.csv` tiene
32.343 registros y 67 columnas; es el join de vivienda y módulo por `FOLIO`.

`ml/data/load_enape.py` hace la preparación completa:

| Paso | Regla | Resultado |
|---|---|---|
| Cohorte | `inscrito == 1` (cursó 2020-2021), `EDAD >= 6`, `inscrito_actual ∈ {1,2}`, `nins_causa != 4` | 18.207 filas |
| Etiqueta | `abandono = 1` si `inscrito_actual == 2` (no se reinscribió en 2021-2022) | 1.179 positivos (6,48 %) |
| Renombres | `SEXO→sexo`, `ENT→ent`, `InternetF→internet_f`, `x<30→menores_30`, `EDAD→edad` | contrato snake_case |
| Binarias | 1 = sí / 2 = no → 1 / 0 | 8 columnas en {0,1} |
| Salida | `ml/data/enape.csv` (FOLIO + 18 variables + etiqueta + etiqueta legible) | 18.207 × 21 |

**Las 18 variables del contrato** (`FEATURES` en `load_enape.py`, en orden fijo):
`sexo, edad, edu_inicial, nivel_edu, terminado, ent, q_personas, q_hombres,
q_mujeres, menores_30, pc, laptop, tv_plana, tablet, smartphone, internet_f,
max_nivel_esp, entr_diagnost`.

**Fuga estructural.** `max_nivel_esp` y `entr_diagnost` sólo se preguntan a quien
sigue inscrito, así que su código 0 delata la etiqueta (ROC-AUC espuria ≈ 1.0).
Se quedan en el contrato de la API, pero **el modelo entrena con 16 variables**
(`MODEL_FEATURES` en `ml/pipeline/modeling.py`). Por la misma razón se excluyen
`nins_causa`, `nt_causa` y todo el bloque condicionado a estar inscrito
(materiales, `med_*`, `t_*`, estrés/depresión, asesorías, `ev_*`, recursado).

Verificación rápida:

```powershell
python -m ml.data.load_enape        # 18.207 filas, 6,48 % positivos
python -m ml.data.validate --data ml/data/enape.csv --report outputs/validation.json
```

El reporte de validación debe salir `ok: true`, con 0 filas inválidas y ~127
duplicados (0,7 %), por debajo del 5 % permitido.

**Dónde se ven estos números en el front.** `docs/dashboard.html` tiene dos
secciones alimentadas por `docs/datos-despliegue.json`:

- **El conjunto de datos**: registros del archivo original (32.343), registros de
  la cohorte (18.207), variables observadas (18) y usadas por el modelo (16),
  duplicados descartados (127), la distribución `Continua` 93,52 % /
  `Abandona` 6,48 % y la nota de la cohorte.
- **Resultados del modelo**: ROC-AUC 0.862, PR-AUC 0.404, recall de `Abandona`
  0.712, exactitud 85,78 %, la tabla de precisión/recall/F1 por clase y el
  contador de pruebas automáticas (52/52).

Se regeneran con `pwsh -File scripts/build_dashboard.ps1` (o `-SkipTests`).

---

## 3. Las etapas, una por una

Todo se lanza con un único script:

```powershell
$env:TF_PLUGIN_CACHE_DIR = "C:\Users\<usuario>\tf-plugin-cache"   # ver §7
pwsh -File scripts/azure_up.ps1 -Stage <etapa> -ImageTag v3
```

| Etapa | Función en `azure_up.ps1` | Qué crea o hace | Archivos que toca |
|---|---|---|---|
| `preflight` | `Invoke-Preflight` | Valida `az`, `terraform`, Docker y sesión. No crea nada. | — |
| `state` | `Invoke-State` | RG `rg-tfstate-mlops`, storage versionado, contenedor `tfstate`, `backend.hcl` | `providers.tf` (backend) |
| `base` | `Invoke-Base` | `terraform init/plan/apply` de todo menos el ACI | `main.tf`, `training.tf`, `datafactory.tf`, `monitoring.tf`, `inference.tf` (RBAC) |
| `data` | `Invoke-Data` | Sube `enape.csv` a `raw/`, corre ADF, registra el Data Asset | `ml/data/*.sh`, `datafactory.tf`, `.dfs` |
| `train` | `Invoke-Train` | Crea el job de Azure ML y espera a `Completed` | `ml/pipeline/job.yaml`, `ml/` |
| `image` | `Invoke-Image` | Descarga el modelo, `docker build`, `push` a ACR | `endpoint/Dockerfile` |
| `aci` | `Invoke-Aci` | `terraform apply -target=...inference` con `deploy_aci=true` | `inference.tf` |
| `verify` | `Invoke-Verify` | `/health`, `/predict` sin y con key, `/feedback` | `endpoint/app.py` |
| `stop` | `Invoke-Stop` | `az container stop` (conserva el recurso) | — |
| `destroy` | `Invoke-Destroy` | `terraform destroy` + purga del Key Vault | todos los `.tf` |

### Etapa 0 — `preflight`

No toca Azure. Comprueba que existan `az`, `terraform`, `docker` y que haya
sesión (`az account show`), imprime los nombres derivados y avisa si el resource
group ya existe o si la cuota `standardDSv3Family` está en 0.

**Por qué importa:** es la única forma de detectar que estás en la suscripción
equivocada antes de gastar. La suscripción esperada es
`Azure subscription 1` (`d0dfb29a-…`).

### Etapa 1 — `state` (estado remoto)

Terraform necesita un lugar donde guardar el `.tfstate`. Si vive en tu portátil,
dos personas (o dos pipelines) pueden aplicar a la vez y corromperlo.

- Crea `rg-tfstate-mlops` y `sttfstatemlopslab` **fuera** del resource group del
  proyecto: sobreviven al `destroy`, así que mañana no hay que reimportar nada.
- Activa *versionado de blobs*: si un `apply` deja el state inconsistente,
  puedes recuperar la versión anterior.
- Asigna `Storage Blob Data Contributor` a tu usuario (el pipeline usa su propia
  identidad).
- Genera `terraform/backend.hcl` con `resource_group_name`, `storage_account_name`,
  `container_name` y `key`.

Declaración del backend: `terraform/providers.tf`. El bloque `backend "azurerm" {}`
está vacío a propósito: los valores llegan por `-backend-config backend.hcl`, de
modo que el mismo código sirve para dev y para el pipeline.

**En el portal:** Storage accounts → `sttfstatemlopslab` → Containers → `tfstate`
→ `mlopslab-dev.tfstate`. Cada `apply` añade una versión nueva.

### Etapa 2 — `base` (la infraestructura)

Es la etapa grande: un solo `terraform apply` crea 26 de los 27 recursos.

Orden real de creación (lo impone el grafo de dependencias de Terraform, no el
orden de los archivos):

```text
rg-mlopslab-dev
├── stmlopslabdev001            (main.tf)   Storage LRS, blobs privados
│   ├── raw                     (main.tf)   CSV crudo de ENAPE
│   └── processed               (main.tf)   salida de ADF
├── kv-mlopslab-dev             (main.tf)   sin purge protection (dev)
├── acrmlopslabdev              (main.tf)   SKU Basic, admin_enabled
├── log-mlopslab-dev            (main.tf)   PerGB2018, 30 días
├── appi-mlopslab-dev           (main.tf)   telemetría del workspace
├── mlw-mlopslab-dev            (main.tf)   workspace Azure ML (Basic)
│   ├── cpu-cluster             (training.tf) DS3_v2, 0–2 nodos
│   ├── raw_data                (training.tf) datastore → contenedor raw
│   └── processed_data          (training.tf) datastore → contenedor processed
├── adf-mlopslab-dev            (datafactory.tf) identidad administrada
│   ├── ls_storage              (datafactory.tf) StorageV2 + managed identity
│   ├── ds_raw_enape            (datafactory.tf) raw/enape/latest/enape.csv
│   ├── ds_processed_enape      (datafactory.tf) processed/enape/latest/
│   ├── ds_rejected_enape       (datafactory.tf) raw/rejected/enape/
│   ├── df_clean_enape          (datafactory.tf) el Data Flow
│   └── pl_clean_enape          (datafactory.tf) pipeline que lo ejecuta
├── ag-mlopslab-dev             (inference.tf) action group de alertas
├── alert-…-latency-p99         (monitoring.tf)
├── workbook MLOps              (monitoring.tf)
└── RBAC                        (main.tf / inference.tf)
```

Dos asignaciones de rol merecen atención porque su ausencia produce fallos
silenciosos:

- `workspace_acr_push` / `workspace_acr_pull` (`main.tf`). Azure ML construye la
  imagen del environment de cada job y la publica en el ACR del workspace. Sin
  `AcrPush`, el job se queda en **`Preparing` para siempre** y el clúster nunca
  escala, sin ningún error en pantalla.
- `adf_blob` (`datafactory.tf`). Sin `Storage Blob Data Contributor` para la
  identidad de ADF, el Data Flow falla con `403`.

**En el portal:** Resource groups → `rg-mlopslab-dev` → *Overview*. Ahí están los
recursos de primer nivel; el resto (datasets, data flow, datastores) cuelga de
ADF o del workspace y se ve en sus propias hojas.

**Verificación:**

```powershell
cd terraform; terraform output; cd ..
az resource list -g rg-mlopslab-dev --query "length(@)"
```

### Etapa 3 — `data` (Blob → Data Factory → Data Asset)

Es la etapa que más gente salta y la que más valor tiene para la rúbrica: aquí
está el ETL real, no un `pandas.read_csv` disfrazado.

**Paso 1 — subida** (`ml/data/upload_to_blob.sh`)

```text
raw/enape/<YYYYMMDDHHMM>/enape.csv   ← copia versionada, para auditoría
raw/enape/latest/enape.csv           ← la que lee ADF
```

Se usa `--auth-mode login`, es decir Azure AD (`Storage Blob Data Contributor`),
nunca una connection string. Ese permiso lo crea `inference.tf`
(`deployer_blob`).

**Paso 2 — limpieza en ADF** (`pl_clean_enape` → `df_clean_enape`)

El pipeline tiene **una sola actividad**: `ExecuteDataFlow`, con 8 núcleos y
`traceLevel: Fine`. El trabajo real está en `dataflows/clean_enape.dfs`:

| Transformación | Qué hace |
|---|---|
| `SplitRows` | `split()` con la condición de rechazo: columnas nulas, `inscrito != 1`, edad fuera de 6–100, `inscrito_actual ∉ {1,2}`, `nins_causa == 4`, binarias fuera de {1,2}, `ENT` fuera de 1–32, etc. Genera dos ramas: `Valid` y `Rejected`. |
| `DeriveFeatures` | Renombra al contrato, recodifica 1/2 → 1/0, deriva `abandono` y `abandono_label`. |
| `SelectFeatures` | Deja `FOLIO` + 18 variables + etiqueta + etiqueta legible. |
| `DistinctRows` | `aggregate(groupBy(row_hash = sha2(256, columns())))` — deduplica por hash de **todas** las columnas. |
| `DropHash` | `select` que elimina la columna auxiliar `row_hash`. |
| `ProcessedCsv` | sink a `processed/enape/latest/enape.csv`, `truncate: true`. |
| `RejectedCsv` | sink a `raw/rejected/enape/rejected.csv`. |

Detalle que costó una corrida fallida: el linked service `ls_storage` necesita
`storage_kind = "StorageV2"` (`datafactory.tf`). Sin eso, Data Flow asume
Storage v1 y rechaza la identidad administrada con `DFExecutorUserError`.

**Paso 3 — Data Asset** (`run_adf_pipeline.sh`)

Hace `az datafactory pipeline create-run`, espera el `runId` hasta `Succeeded`
(máximo 30 min) y registra la salida como data asset versionado:

```powershell
az ml data create --name enape-abandono --version <YYYYMMDDHHMM> `
  --path azureml://datastores/processed_data/paths/enape/<versión>/enape.csv
```

**Por qué versionar:** el job de entrenamiento referencia
`azureml:enape-abandono@latest`, y la copia inmutable permite reproducir
exactamente los datos de una corrida anterior.

**En el portal:**
- Data factories → `adf-mlopslab-dev` → *Author* → Pipelines / Data flows.
- *Monitor* → Pipeline runs. La primera ejecución puede fallar por propagación
  de RBAC (5–15 min es normal); no es un bug del código.
- Azure ML Studio → *Data* → `enape-abandono`.

### Etapa 4 — `train` (job de Azure ML)

`ml/pipeline/job.yaml` describe el job y `code: .` incluye la raíz del proyecto (la CLI se ejecuta desde el root del repo):

- `compute: azureml:cpu-cluster` (0 nodos en reposo → escala al arrancar).
- `environment`: imagen base de Azure ML + `requirements.txt`.
- `inputs`: el data asset `enape-abandono`.
- `command`: `python -m ml.pipeline.train --model-name enape-abandono`.

Qué hace `train.py`:

1. Carga el CSV desde el input montado por Azure ML.
2. Divide 80/20 estratificado.
3. Entrena un `RandomForestClassifier` (300 árboles, profundidad 10,
   `class_weight="balanced_subsample"`) sobre las 16 variables del modelo.
4. Calcula accuracy, F1 macro, **ROC-AUC**, **PR-AUC**, métricas por clase y
   matriz de confusión; loguea todo en **MLflow**.
5. Guarda el perfil de referencia para data drift y la importancia de variables.
6. Registra el modelo como `enape-abandono` en el Model Registry, en stage
   **Staging** — nunca promueve solo.

**Gate de calidad** (`ml/pipeline/evaluate.py`). Con 6,5 % de positivos la
accuracy es engañosa, así que el gate no la usa:

| Regla | Umbral | Por qué |
|---|---|---|
| PR-AUC | ≥ 0.35 | mide la calidad sobre la clase que importa (`Abandona`) |
| Recall de `Abandona` | ≥ 0.60 | no se acepta un modelo que ignore abandonos |
| Regresión vs Production | ≤ 0.005 de caída en PR-AUC | evita desplegar algo peor |
| Misma versión | prohibido | compararse consigo mismo aprobaría siempre |

Resultado de la validación local del 18-11: **ROC-AUC 0.862, PR-AUC 0.404,
recall de `Abandona` 0.712** → el candidato pasa el gate.

Restricción del entorno: con la extensión `ml` 2.45.2, `az ml job stream` aborta
con `binascii.Error: Incorrect padding` aunque el job siga vivo. El script usa
polling con `az ml job show --query status` cada 30 s (máximo 120 min).

La primera corrida tarda 10–15 min porque aprovisiona la VM `Standard_DS3_v2`
desde cero. `.amlignore` evita subir entornos virtuales, CSV derivados, salidas generadas, cachés y estado de Terraform; conserva el código y las definiciones necesarios para el job y el despliegue.

**En el portal:** Azure ML Studio → *Jobs* → `enape-training` → el job de la
corrida. Pestañas útiles: *Metrics* (MLflow), *Outputs + logs*
(`user_logs/std_log.txt`), *Models*.

### Etapa 5 — `image` (Docker → ACR)

1. `download_model.sh` baja del Model Registry la versión en **Production**; si
   no hay ninguna, la más reciente. Escribe `endpoint/model/enape-abandono/` y
   `registered_model_meta` (de ahí sale el `model_version` que reporta
   `/health`).
   Sin Azure, `scripts/export_local_model.py` empaqueta el `model.pkl` local con
   el mismo formato.
2. `docker build -t acrmlopslabdev.azurecr.io/endpoint:v3 endpoint/`
3. `az acr login` + `docker push` del tag `v3` y de `latest`.

**Por qué no ACR Tasks:** está bloqueado en la suscripción educativa. Se
construye con Docker local o en el agente de Azure Pipelines.

**En el portal:** Container registries → `acrmlopslabdev` → *Repositories* →
`endpoint` → tags (`latest`, `v1`, `v2`, `v3`).

### Etapa 6 — `aci` (inferencia)

```powershell
terraform apply -target=azurerm_container_group.inference `
  -var="deploy_aci=true" -var="endpoint_image_tag=v3"
```

`inference.tf` define el contenedor:

| Atributo | Valor | Por qué |
|---|---|---|
| `count` | `var.deploy_aci ? 1 : 0` | el ACI no existe hasta que hay imagen |
| CPU / RAM | 1 vCPU / 1.5 GB | suficiente para inferencia batch pequeña; ~0.04 USD/h |
| Puerto | 8000 | el mismo que expone `uvicorn` en `app.py` |
| `dns_name_label` | `mlops-mlopslab-dev` | URL estable aunque cambie la IP |
| `identity` | SystemAssigned | permite leer el Key Vault |
| `secure_environment_variables` | `API_KEY`, `APPLICATIONINSIGHTS_CONNECTION_STRING` | no aparecen en el portal ni en `az container show` |
| `liveness_probe` | `GET /health` cada 30 s | ACI reinicia el contenedor si deja de responder |
| `diagnostics.log_analytics` | workspace del proyecto | es el origen de los logs que lee el workbook |

**No usar `az container create`.** Un PUT de la CLI reemplaza el recurso entero y
borra identidad, probe y diagnóstico. El stage `Deploy` del pipeline aplica
Terraform justamente por esto.

**En el portal:** Container instances → `aci-mlopslab-dev-inference` →
*Containers* → *Logs*. Ahí se ven las líneas JSON que escribe `app.py`.

### Etapa 7 — `verify` (prueba funcional real)

El script espera a que `/health` responda, lee `endpoint-api-key` del Key Vault y
ejecuta cuatro pruebas con `endpoint/examples/estudiante_riesgo_alto.json`:

| Prueba | Esperado | Qué demuestra |
|---|---|---|
| `GET /health` | `200`, `model_loaded: true` | el contenedor arrancó y cargó el modelo |
| `POST /predict` sin `X-API-Key` | `401` | la API no está abierta |
| `POST /predict` con key | `200` + clase y `dropout_risk` | el modelo predice de verdad |
| `POST /feedback` | `202` | el bucle de reentrenamiento tiene entrada |

La salida se escribe en `docs/demo-curl-azure.md` con las respuestas completas:
eso es la evidencia que se enseña, no una captura de pantalla.

### Etapa 8 — `stop` y `destroy`

- `stop` → `az container stop`. El recurso sigue existiendo, la IP y el FQDN se
  conservan, pero **el cómputo deja de cobrarse**. Es lo que se hace al terminar
  cada demostración.
- `destroy` → `terraform destroy -var="deploy_aci=true"` (el `-var` es
  obligatorio: sin él, `count = 0` y el ACI quedaría huérfano, cobrando). Después
  purga `kv-mlopslab-dev`, que queda *soft-deleted* y reserva el nombre 7 días.

Detalle que apareció en la práctica del 18-11: Azure crea por su cuenta el
action group **`Application Insights Smart Detection`** dentro del resource
group, y Terraform no lo gestiona. Al destruir el RG, Terraform aborta con
`the Resource Group still contains Resources`. La solución está en
`providers.tf`:

```hcl
provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
```

Con eso el RG se borra completo. Si el state es anterior al cambio, el script
detecta el fallo, ejecuta `az group delete` y repite el destroy para limpiar la
referencia. Verificación final: `terraform state list` debe salir vacío.

Lo que **no** se borra con `destroy`, a propósito:

| Recurso | Por qué se conserva |
|---|---|
| `rg-tfstate-mlops` | sin state, mañana habría que reimportar 27 recursos a mano |
| Los `.tf` y el código | obvio, pero conviene decirlo |

---

## 4. Cómo se conecta todo (flujo de una predicción)

```text
Cliente
  │  POST /predict  {18 variables}  + X-API-Key
  ▼
ACI (contenedor FastAPI, endpoint/app.py)
  │  1. valida la API key contra $API_KEY (viene de Key Vault)
  │  2. valida el esquema Pydantic (18 campos, rangos, sin claves extra)
  │  3. descarta las 2 variables con fuga y arma el vector de 16
  │  4. predice y devuelve {prediction, probabilities, dropout_risk, risk_level}
  │  5. escribe una línea JSON en stdout
  ▼
stdout del contenedor
  │  ACI → diagnostics → Log Analytics
  ▼
ContainerInstanceLog_CL   (tabla que consultan alertas, workbook y drift)
```

Ese último salto es el que hace que el monitoreo sea real y no decorativo: la
alerta `latency-p99` y el workbook leen **la misma tabla** que produce el
endpoint en cada request.

Los nombres de respuesta (`dropout_risk`, `prediction_id`, etc.) se conservaron
del modelo anterior para no romper el workbook KQL ni `demo-curl-azure.md`.

---

## 5. Dónde mirar cuando algo falla

| Síntoma | Primer sitio | Causa típica |
|---|---|---|
| `terraform init` falla con "contains a virus" | `terraform/.terraform` | antivirus de terceros sobre el provider en OneDrive → usar `TF_PLUGIN_CACHE_DIR` |
| El RG existe y el state está vacío | `terraform state list` | se creó a mano o con otro `project_name`; el script aborta a propósito |
| Job en `Preparing` eterno | `az role assignment list --scope <acr-id>` | falta `AcrPush` para el MSI del workspace |
| Data Flow `403` | ADF → Monitor | propagación de RBAC de la identidad de ADF (5–15 min) |
| Data Flow `DFExecutorUserError` … `general purpose v1` | `datafactory.tf` | falta `storage_kind = "StorageV2"` |
| ACI no responde `/health` | `az container logs` | imagen mal construida o `API_KEY` ausente |
| `/health` con `model_version: null` | `endpoint/model/enape-abandono/registered_model_meta` | la imagen se construyó sin metadatos → rehacer `-Stage image` |
| `terraform apply` quiere destruir el ACI | `terraform plan` | `deploy_aci` volvió a `false` |
| `pytest` falla por `dropout.csv` | `ml/tests/test_data.py` | dataset UCI anterior; el contrato es ENAPE (`enape.csv`) |

---

## 6. Costos: qué cuesta y qué no

| Recurso | Modelo | En reposo |
|---|---|---|
| ACR Basic | fijo | ~5 USD/mes (el mayor gasto fijo) |
| Storage (LRS, pocos MB) | por GB | céntimos |
| Log Analytics | por GB ingerido | ~0 si no hay tráfico |
| Key Vault | por operación | ~0 |
| ADF | por actividad + DIU-hora | 0 si no corre |
| Compute cluster | por nodo-minuto | **0 con `min_nodes = 0`** |
| ACI | por segundo de CPU/RAM | **0 con `stop`** |
| Azure ML workspace | gratis (Basic) | 0 |

Con todo desplegado pero apagado, el gasto es de unos **9–10 USD/mes**,
prácticamente todo el ACR. Con el ACI encendido se suman ~0.04 USD/h; un job de
entrenamiento de 12 min en `Standard_DS3_v2` cuesta ~0.15 USD. Detalle en
`docs/costos.md`.

---

## 7. Las tres trampas de este entorno

Están aquí porque van a volver a aparecer mañana:

1. **Antivirus + OneDrive.** *Reason Cybersecurity* marca el provider
   `azurerm.exe` (238 MB) al escribirlo dentro de OneDrive y `terraform init`
   muere. Solución: `$env:TF_PLUGIN_CACHE_DIR = "C:\Users\<usuario>\tf-plugin-cache"`
   **antes** de ejecutar el script. No se desactiva el antivirus.
2. **PowerShell 7.7 parte argumentos.** `-backend-config=backend.hcl` se
   convierte en dos tokens y Terraform responde `No positional arguments are
   expected`. Usar la forma con espacio (`-backend-config backend.hcl`); el
   script ya lo hace.
3. **`az ml job stream` está roto** en la extensión 2.45.2
   (`binascii.Error: Incorrect padding`). El job sigue corriendo: consultar con
   `az ml job show --query status`.

---

## 8. Qué está probado y qué no

| Pieza | Estado | Evidencia |
|---|---|---|
| Dataset ENAPE 2021 | ✅ 18.207 filas, 6,48 % positivos, validación `ok` | `outputs/validation.json` |
| Modelo `enape-abandono` | ✅ ROC-AUC 0.862 / PR-AUC 0.404 / recall 0.712, gate superado | `outputs/metrics_enape.json` |
| Pruebas automáticas | ✅ 52/52 | `python -m pytest -q` |
| Terraform | ✅ `fmt` y `validate` sin errores | `terraform validate` |
| Infraestructura Terraform | ✅ 27 recursos en la corrida del 17-11; eliminada el 18-11 | `docs/despliegue-azure.md` §6 |
| ETL en Data Factory | ✅ corrida `Succeeded` (UCI); pipeline ENAPE definido | ADF → Monitor |
| Entrenamiento en Azure ML | ✅ job `mighty_nut_8jvyq81p06` `Completed` (UCI) | ML Studio → Jobs |
| Model Registry | ✅ `dropout-classifier` v1 en Staging (histórico) | ML Studio → Models |
| Imagen en ACR | ✅ `endpoint:v1` y `:v2` (histórico) | ACR → Repositories |
| Endpoint ACI | ✅ 4/4 pruebas el 17-11 | `docs/demo-curl-azure.md` |
| Monitoreo | ✅ 3 alertas + action group + workbook | Azure Monitor |
| Pipeline Azure DevOps | ⏳ definido, sin ejecutar | falta service connection ARM + variable group |
| `drift-monitoring.yml` programado | ⏳ mismo bloqueo | — |
| Relanzamiento con ENAPE | ⏳ `-Stage all -ImageTag v3` | pendiente para la demo |
