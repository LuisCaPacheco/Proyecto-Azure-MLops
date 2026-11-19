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

`training.tf` (Etapas 1-2):

- `azurerm_machine_learning_compute_cluster` `cpu-cluster` - `Standard_DS3_v2`, 0-4 nodos (ajustar el máximo según la cuota regional disponible)
- `azurerm_machine_learning_datastore_blobstorage` `raw_data` / `processed_data` - datastores del workspace

`datafactory.tf` (Etapa 2):

- `azurerm_data_factory` + linked service al Storage con identidad administrada
  (`storage_kind = "StorageV2"`)
- 3 datasets: `ds_raw_enape` (`raw/enape/latest/enape.csv`), `ds_processed_enape`
  (`processed/enape/latest/`) y `ds_rejected_enape` (`raw/rejected/enape/`)
- `azurerm_data_factory_data_flow` `df_clean_enape` (script en
  `dataflows/clean_enape.dfs`) y `azurerm_data_factory_pipeline` `pl_clean_enape`:
  aplican la cohorte ENAPE 2021, descartan filas inválidas y duplicados y dejan
  la salida en `processed/enape/latest/enape.csv`

`inference.tf` (Etapas 3-4):

- `random_password` + `azurerm_key_vault_secret` `endpoint-api-key` - API key del endpoint, solo en Key Vault
- `azurerm_key_vault_access_policy` - permiso de escritura de secretos para quien ejecuta Terraform
- `azurerm_container_group` (ACI, con `deploy_aci = true`) - endpoint con variables seguras,
  liveness probe y logs hacia Log Analytics
- `azurerm_role_assignment` - roles diferenciados (AzureML Data Scientist / Reader)
- `azurerm_monitor_action_group` + alertas de CPU del ACI y errores del endpoint

`monitoring.tf` (Etapa 4):

- alerta de latencia P99 de inferencia (`latency_p99_threshold_ms`, por defecto 500 ms)
- `azurerm_application_insights_workbook` - tablero de Azure Monitor sobre los logs del endpoint

## Requisitos previos

- Azure CLI (`az`) autenticado: `az login`
- Terraform >= 1.5

## Uso

```bash
az login
bash ../scripts/bootstrap_tfstate.sh        # una sola vez: cuenta para el estado remoto
cp backend.hcl.example backend.hcl          # ajustar nombres si se cambiaron
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl  # con estado local previo: agregar -migrate-state
terraform validate
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform apply tfplan
```

`terraform.tfvars.example` usa `project_name = "mlopslab"`, igual que los YAML
de Azure Pipelines. Si cambias `project_name` o `environment`, cambia también la
variable `project`/`env` de los pipelines y la `key` de `backend.hcl`.

El estado vive en Azure Blob Storage (`backend.tf`), compartido por el equipo y con bloqueo.
`tfplan` y `backend.hcl` no se versionan (un plan puede contener secretos).

## Personalización

Edita `variables.tf` o pasa variables en la línea de comandos:

```bash
terraform apply -var="location=westeurope" -var="environment=dev"
```

## Notas

- **Compute cluster de entrenamiento** (`Standard_DS3_v2`, 0-4 nodos): ahora es un recurso de Terraform (`training.tf`). Si ya existía porque se creó con `az ml compute create`, hay que importarlo antes del `apply`:
  `terraform import azurerm_machine_learning_compute_cluster.cpu "<id del workspace>/computes/cpu-cluster"`
  (el id sale de `terraform output -raw ml_workspace_id`).
  Si la cuota de vCPU de la suscripción no alcanza para 4 nodos (16 vCPU), bajar `compute_max_nodes`.
- **ACI**: Terraform es el único dueño del contenedor (identidad, liveness probe,
  variables seguras y diagnóstico a Log Analytics). El stage Deploy del pipeline
  hace un `terraform apply -target=azurerm_container_group.inference` con el
  nuevo `endpoint_image_tag`; **no** se debe recrear con `az container create`
  porque un PUT de la CLI borra esa configuración.
- El nombre del storage account y ACR deben ser únicos globalmente; ajusta `project_name` si colisiona.
- El ACI se crea con `-var="deploy_aci=true"` cuando la imagen esté en ACR:
  `terraform plan -var-file=terraform.tfvars -var="deploy_aci=true" -var="endpoint_image_tag=v2" -out=aci.tfplan`
  y luego `terraform apply aci.tfplan`. Mantén `deploy_aci=true` en los applies
  posteriores: si vuelve a `false`, Terraform **destruye** el ACI.
- La métrica `CpuUsage` de ACI se mide en núcleos (1 vCPU = 1.0); por eso
  `aci_cpu_alert_threshold` vale `0.8` y no `800`.
- `terraform destroy` debe usar las mismas variables que el apply (incluido
  `deploy_aci=true`) para que el ACI esté en el state y se elimine. El Key Vault
  queda soft-deleted y reserva el nombre: en dev no tiene purge protection y
  `scripts/azure_up.ps1 -Stage destroy` lo purga al final.
- Configuración validada con `terraform fmt -check` y `terraform validate` (Terraform 1.17.1).
