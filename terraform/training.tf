# ---------------------------------------------------------------------------
# Etapa 1-2: cómputo de entrenamiento y datastores del ML Workspace
# ---------------------------------------------------------------------------

# Compute cluster de entrenamiento (Standard_DS3_v2, 0-4 nodos).
# Con min = 0 solo se cobra mientras corre un job.
#
# Si el cluster ya fue creado antes con `az ml compute create`, impórtelo al
# estado en lugar de recrearlo:
#   terraform import azurerm_machine_learning_compute_cluster.cpu \
#     "<id del workspace>/computes/cpu-cluster"
resource "azurerm_machine_learning_compute_cluster" "cpu" {
  name                          = "cpu-cluster"
  location                      = azurerm_resource_group.main.location
  machine_learning_workspace_id = azurerm_machine_learning_workspace.main.id
  vm_size                       = var.compute_vm_size
  vm_priority                   = var.compute_vm_priority
  description                   = "Cluster CPU para los jobs de entrenamiento"
  tags                          = local.tags

  scale_settings {
    min_node_count = var.compute_min_nodes
    max_node_count = var.compute_max_nodes
    # PT2M es la forma que normaliza la API (PT120S fuerza reemplazo del clúster)
    scale_down_nodes_after_idle_duration = "PT2M"
  }

  identity {
    type = "SystemAssigned"
  }
}

# Datastores del workspace sobre los contenedores raw / processed.
# `raw_data`: lo que llega de la fuente. `processed_data`: la salida limpia
# del pipeline de Azure Data Factory, que es lo que consume el entrenamiento.
resource "azurerm_machine_learning_datastore_blobstorage" "raw" {
  name                 = "raw_data"
  workspace_id         = azurerm_machine_learning_workspace.main.id
  storage_container_id = azurerm_storage_container.raw.resource_manager_id
  account_key          = azurerm_storage_account.main.primary_access_key
  description          = "Datos crudos (contenedor raw)"
}

resource "azurerm_machine_learning_datastore_blobstorage" "processed" {
  name                 = "processed_data"
  workspace_id         = azurerm_machine_learning_workspace.main.id
  storage_container_id = azurerm_storage_container.processed.resource_manager_id
  account_key          = azurerm_storage_account.main.primary_access_key
  description          = "Datos depurados por Azure Data Factory (contenedor processed)"
}
