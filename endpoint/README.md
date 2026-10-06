# Endpoint de Inferencia (Etapa 3)

API REST (FastAPI) que sirve `dropout-classifier` — la versión en Production del
Model Registry — empaquetada como imagen Docker y desplegada en Azure Container
Instances (ACI).

## Estructura

```
endpoint/
├── Dockerfile          # python:3.12-slim, usuario no-root, healthcheck
├── app.py              # FastAPI: /health, /model-info, /predict, /predict/batch, /explain
├── explain.py          # Contribución de cada variable a P(Dropout)
├── requirements.txt    # scikit-learn fijado a la versión de entrenamiento
├── download_model.sh   # Baja la versión Production del Model Registry a ./model
├── model/              # Modelo MLflow (MLmodel + model.pkl + metrics.json)
├── examples/           # Solicitudes de ejemplo (riesgo alto/bajo, lote)
└── tests/              # 12 pruebas: esquema, errores, API key, rate limit, explicabilidad
```

## Contrato

`POST /predict` acepta **uno** de:

```json
{"student": {"marital_status": 1, "application_mode": 17, "...": 0, "gdp": 1.74}}
{"features": [1, 17, 5, 171, ...]}      // 36 valores en el orden de GET /model-info
```

Respuesta:

```json
{"prediction": "Dropout", "class_index": 0, "confidence": 0.8515,
 "probabilities": {"Dropout": 0.8515, "Enrolled": 0.1287, "Graduate": 0.0199},
 "dropout_risk": 0.8515, "risk_level": "alto", "model_version": "2"}
```

`POST /explain?top=6` devuelve además los factores que suben o bajan P(Dropout):

```json
{"target_class": "Dropout", "base_probability": 0.3333, "predicted_probability": 0.8515,
 "top_factors": [{"feature": "tuition_fees_up_to_date", "value": 0.0, "contribution": 0.3092, "effect": "aumenta"},
                 {"feature": "curricular_units_1st_sem_approved", "value": 2.0, "contribution": 0.0707, "effect": "aumenta"}]}
```

Códigos: `400` entrada inválida (features faltantes/sobrantes, número incorrecto),
`401` sin API key válida, `422` tipos erróneos, `429` límite de solicitudes.

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `API_KEY` | (vacía = sin auth, solo local) | Valor esperado en `X-API-Key`; en ACI viene de Key Vault |
| `RATE_LIMIT_PER_MIN` | 60 | Solicitudes por minuto por IP |
| `RISK_HIGH` / `RISK_MEDIUM` | 0.5 / 0.3 | Umbrales de P(Dropout) para el nivel de riesgo |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | Activa la telemetría hacia App Insights |
| `LOG_FEATURES` | true | Incluir las variables en el log (insumo del monitor de drift) |

## 1. Obtener el modelo

```bash
./download_model.sh mlw-mlopsproj-dev rg-mlopsproj-dev   # desde Azure ML
python scripts/export_production_model.py                # o desde el MLflow local
```

## 2. Pruebas

```bash
pip install -r requirements.txt pytest httpx
pytest tests -v
```

## 3. Construir, probar y publicar

```bash
docker build -t acrmlopsprojdev.azurecr.io/endpoint:v2 .
docker run -d -p 8000:8000 -e API_KEY=demo acrmlopsprojdev.azurecr.io/endpoint:v2
curl -s -X POST localhost:8000/predict -H "X-API-Key: demo" -H "Content-Type: application/json" \
  -d @examples/estudiante_riesgo_alto.json

az acr login --name acrmlopsprojdev
docker push acrmlopsprojdev.azurecr.io/endpoint:v2
```

ACR Tasks está bloqueado en la suscripción educativa, por eso se construye con Docker local
(o en el agente de Azure Pipelines).

## 4. Desplegar en ACI

```bash
cd ../terraform
terraform init -upgrade
terraform apply -var="deploy_aci=true" -var="endpoint_image_tag=v2"
terraform output endpoint_url
```

La API key queda en Key Vault (`endpoint-api-key`) y se inyecta como variable segura.
