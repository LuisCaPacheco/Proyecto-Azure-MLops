# Endpoint de Inferencia (Etapa 3)

API REST (FastAPI) que sirve `enape-abandono` — la versión en Production del
Model Registry — empaquetada como imagen Docker y desplegada en Azure Container
Instances (ACI).

Predice si un estudiante de la cohorte ENAPE 2021 **continúa** o **abandona** sus
estudios, a partir de 18 variables observadas antes del ciclo.

## Estructura

```
endpoint/
├── Dockerfile          # python:3.12-slim, usuario no-root, healthcheck
├── app.py              # FastAPI: /health, /model-info, /predict, /predict/batch, /explain, /feedback
├── explain.py          # Contribución de cada variable a P(Abandona)
├── requirements.txt    # scikit-learn fijado a la versión de entrenamiento
├── download_model.sh   # Baja la versión Production del Model Registry a ./model
├── model/              # Artefacto MLflow (MLmodel + model.pkl + metrics.json)
├── examples/           # Solicitudes de ejemplo (riesgo alto/bajo, lote)
└── tests/              # esquema, errores, API key, rate limit, explicabilidad
```

## Contrato

`POST /predict` acepta **uno** de:

```json
{"student": {"sexo": 0, "edad": 15, "edu_inicial": 0, "nivel_edu": 4, "...": 0}}
{"features": [0, 15, 0, 4, 1, 20, 5, 2, 3, 1, 1, 0, 1, 0, 1, 0, 0, 0]}
```

Las **18 variables**, en el orden que devuelve `GET /model-info`:
`sexo, edad, edu_inicial, nivel_edu, terminado, ent, q_personas, q_hombres,
q_mujeres, menores_30, pc, laptop, tv_plana, tablet, smartphone, internet_f,
max_nivel_esp, entr_diagnost`. Las llaves desconocidas se rechazan (`422`).

El modelo usa 16: `max_nivel_esp` y `entr_diagnost` se aceptan por contrato pero
se descartan por fuga estructural.

Respuesta (valores ilustrativos):

```json
{"prediction": "Abandona", "class_index": 1, "confidence": 0.72,
 "probabilities": {"Continua": 0.28, "Abandona": 0.72},
 "dropout_risk": 0.72, "risk_level": "alto",
 "prediction_id": "3f1c0b9e-...", "model_version": "1"}
```

> `dropout_risk` es P(Abandona) y conserva el nombre anterior para no romper el
> workbook KQL ni `docs/demo-curl-azure.md`. `risk_level` = alto ≥ 0.5,
> medio ≥ 0.3, bajo por debajo.

`POST /explain?top=6` devuelve además los factores que suben o bajan P(Abandona):

```json
{"target_class": "Abandona", "base_probability": 0.0648, "predicted_probability": 0.72,
 "top_factors": [{"feature": "nivel_edu", "value": 4.0, "contribution": 0.12, "effect": "aumenta"},
                 {"feature": "internet_f", "value": 0.0, "contribution": 0.08, "effect": "aumenta"}]}
```

Códigos: `400` entrada inválida (número incorrecto de features), `401` sin API
key válida, `422` tipos/rangos erróneos o claves faltantes/sobrantes, `429`
límite de solicitudes.

`POST /feedback` recibe `{"prediction_id": "...", "actual": "Abandona"}` y
devuelve `202`; es la entrada del monitor de accuracy.

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `API_KEY` | (vacía = sin auth, solo local) | Valor esperado en `X-API-Key`; en ACI viene de Key Vault |
| `RATE_LIMIT_PER_MIN` | 60 | Solicitudes por minuto por IP |
| `RISK_HIGH` / `RISK_MEDIUM` | 0.5 / 0.3 | Umbrales de P(Abandona) para el nivel de riesgo |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | Activa la telemetría hacia App Insights |
| `LOG_FEATURES` | true | Incluir las variables en el log (insumo del monitor de drift) |

## 1. Obtener el modelo

```bash
./download_model.sh mlw-mlopslab-dev rg-mlopslab-dev   # desde Azure ML
python scripts/export_local_model.py                     # o desde el modelo local (outputs/model)
python scripts/export_production_model.py                # o desde el MLflow local
```

## 2. Pruebas

```bash
pip install -r requirements.txt pytest httpx
pytest tests -v
```

## 3. Construir, probar y publicar

```bash
docker build -t acrmlopslabdev.azurecr.io/endpoint:v3 .
docker run -d -p 8000:8000 -e API_KEY=demo acrmlopslabdev.azurecr.io/endpoint:v3
curl -s -X POST localhost:8000/predict -H "X-API-Key: demo" -H "Content-Type: application/json" \
  -d @examples/estudiante_riesgo_alto.json

az acr login --name acrmlopslabdev
docker push acrmlopslabdev.azurecr.io/endpoint:v3
```

ACR Tasks está bloqueado en la suscripción educativa, por eso se construye con Docker local
(o en el agente de Azure Pipelines).

## 4. Desplegar en ACI

Terraform es el único dueño del ACI (identidad, liveness probe, variables
seguras y diagnóstico a Log Analytics). Desde la raíz del repo:

```powershell
.\scripts\azure_up.ps1 -Stage aci -ImageTag v3
.\scripts\azure_up.ps1 -Stage verify
```

Equivalente manual:

```bash
cd terraform
terraform init -backend-config backend.hcl
terraform plan -var="deploy_aci=true" -var="endpoint_image_tag=v3" -target=azurerm_container_group.inference -out=aci.tfplan
terraform apply aci.tfplan
terraform output endpoint_url
```

No uses `az container create`: un PUT de la CLI borraría la identidad, el probe
y el diagnóstico del contenedor. La guía completa está en
`docs/despliegue-azure.md`.

La API key queda en Key Vault (`endpoint-api-key`) y se inyecta como variable segura.
