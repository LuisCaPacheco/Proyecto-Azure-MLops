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

`inference.tf` (Etapas 3-4):

- `random_password` + `azurerm_key_vault_secret` `endpoint-api-key` - API key del endpoint, solo en Key Vault
- `azurerm_key_vault_access_policy` - permiso de escritura de secretos para quien ejecuta Terraform
- `azurerm_container_group` (ACI, con `deploy_aci = true`) - endpoint con variables seguras,
  liveness probe y logs hacia Log Analytics
- `azurerm_role_assignment` - roles diferenciados (AzureML Data Scientist / Reader)
- `azurerm_monitor_action_group` + alertas de CPU del ACI y errores del endpoint

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
- El ACI se crea solo con `-var="deploy_aci=true"` cuando la imagen esté en ACR:
  `terraform init -upgrade && terraform apply -var="deploy_aci=true" -var="endpoint_image_tag=v2"`.
  `init -upgrade` es necesario por el nuevo provider `random`.
- Configuración validada con `terraform fmt -check` y `terraform validate` (Terraform 1.9.8).
