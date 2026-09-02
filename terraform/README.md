# Proyecto_Azure_MLOps - Terraform

Este directorio contiene la infraestructura como código del Proyecto 07 (Plataforma MLOps en Azure).

## Recursos aprovisionados

- `azurerm_resource_group` - Resource Group
- `azurerm_storage_account` + contenedores `raw` / `processed` - almacenamiento de datos
- `azurerm_key_vault` - gestión de secretos
- `azurerm_container_registry` (ACR) - imágenes Docker del endpoint
- `azurerm_log_analytics_workspace` - centralización de logs
- `azurerm_application_insights` - telemetría / monitoreo
- `azurerm_machine_learning_workspace` - Azure ML Workspace
- ACI (comentado) - se activa en la fase 5-6 para el endpoint de inferencia

## Requisitos previos

- Azure CLI (`az`) autenticado: `az login`
- Terraform >= 1.5

## Uso

```bash
az login
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

## Personalización

Edita `variables.tf` o pasa variables en la línea de comandos:

```bash
terraform apply -var="location=westeurope" -var="environment=dev"
```

## Notas

- **Compute cluster de entrenamiento** (`Standard_DS3_v2`, 0-4 nodos): se provisiona sobre el ML Workspace usando el CLI de Azure ML (`az ml compute create`), ya que el provider `azurerm` no incluye este recurso. Ver script en la fase 3-4 (`ml/`).
- El nombre del storage account y ACR deben ser únicos globalmente; ajusta `project_name` si colisiona.
- El ACI de inferencia está comentado y se activa cuando la imagen esté en ACR (fases 5-6).
