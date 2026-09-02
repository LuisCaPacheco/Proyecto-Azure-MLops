# Endpoint de Inferencia (Etapa 3)

API REST de inferencia del modelo Iris (FastAPI) empaquetada como imagen Docker
y desplegada en Azure Container Instances (ACI).

## Estructura

```
endpoint/
├── Dockerfile          # Imagen del endpoint (copiamos model/ ya descargado)
├── app.py              # FastAPI: /health, /predict
├── requirements.txt    # Dependencias Python
├── download_model.sh   # Baja el modelo de Production del Model Registry a ./model
├── model/              # Modelo MLflow descargado (generado por download_model.sh)
└── .dockerignore
```

## 1. Descargar el modelo desde el Model Registry

```bash
# Requiere az login + extensión 'ml'
./download_model.sh mlw-mlopsproj-dev rg-mlopsproj-dev
# -> deja el modelo en ./model/iris-classifier/model
```

## 2. Prueba local de la API (opcional)

```bash
pip install -r requirements.txt
MODEL_PATH=$(pwd)/model uvicorn app:app --host 127.0.0.1 --port 8000
curl -s -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" \
  -d '{"features":[5.1,3.5,1.4,0.2]}'
# -> {"prediction":"setosa","confidence":1.0,"class_index":0}
```

## 3. Construir imagen + push a ACR

ACR Tasks está bloqueado en las suscripciones educativas, así que se construye
localmente con Docker y se sube con push.

```bash
cd endpoint

# Login al ACR
az acr login --name acrmlopsprojdev

# Build local (contexto = endpoint/)
docker build -t acrmlopsprojdev.azurecr.io/endpoint:latest .

# Push al ACR
docker push acrmlopsprojdev.azurecr.io/endpoint:latest
```

## 4. Desplegar en Azure Container Instances (ACI)

Una vez la imagen esté en ACR, descomentar el recurso `azurerm_container_group`
del `terraform/main.tf` y aplicar:

```bash
cd ../terraform
terraform plan -out=tfplan
terraform apply tfplan
```

O desplegar con CLI:
```bash
az container create \
  --resource-group rg-mlopsproj-dev \
  --name aci-mlopsproj-dev-inference \
  --image acrmlopsprojdev.azurecr.io/endpoint:latest \
  --registry-login-server acrmlopsprojdev.azurecr.io \
  --registry-username acrmlopsprojdev \
  --registry-password "$(az acr credential show -n acrmlopsprojdev -g rg-mlopsproj-dev --query 'passwords[0].value' -o tsv)" \
  --dns-name-label mlopsprojdev \
  --ports 8000 \
  --cpu 1 \
  --memory 1.5
```

## 5. Probar la inferencia

```bash
curl -s http://mlopsprojdev.centralus.azurecontainer.io:8000/health
curl -s -X POST http://mlopsprojdev.centralus.azurecontainer.io:8000/predict \
  -H "Content-Type: application/json" -d '{"features":[5.1,3.5,1.4,0.2]}'
```
