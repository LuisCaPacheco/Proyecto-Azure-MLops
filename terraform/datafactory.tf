# ---------------------------------------------------------------------------
# Etapa 2: depuración de datos con Azure Data Factory (ETL raw -> processed)
#
#   raw/enape/latest/enape.csv
#        │  Mapping Data Flow `df_clean_enape`
#        ├─► processed/enape/latest/enape.csv   (filas válidas, sin duplicados)
#        └─► raw/rejected/enape/                (filas descartadas, para auditoría)
#
# El stage DataPrep de Azure Pipelines sube el CSV a `raw`, ejecuta el
# pipeline `pl_clean_enape` y registra el Data Asset desde `processed`.
# ---------------------------------------------------------------------------

resource "azurerm_data_factory" "main" {
  name                = "adf-${local.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

# ADF accede al Storage con su identidad administrada (sin claves)
resource "azurerm_role_assignment" "adf_blob" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_data_factory.main.identity[0].principal_id
}

resource "azurerm_data_factory_linked_service_azure_blob_storage" "storage" {
  name                 = "ls_storage"
  data_factory_id      = azurerm_data_factory.main.id
  service_endpoint     = azurerm_storage_account.main.primary_blob_endpoint
  use_managed_identity = true
  # Sin esto, Data Flow asume Storage (general purpose v1) y rechaza la
  # autenticación por identidad administrada con DFExecutorUserError.
  storage_kind = "StorageV2"
}

resource "azurerm_data_factory_dataset_delimited_text" "raw_enape" {
  name                = "ds_raw_enape"
  data_factory_id     = azurerm_data_factory.main.id
  linked_service_name = azurerm_data_factory_linked_service_azure_blob_storage.storage.name

  azure_blob_storage_location {
    container = azurerm_storage_container.raw.name
    path      = "enape/latest"
    filename  = "enape.csv"
  }

  column_delimiter    = ","
  row_delimiter       = "\n"
  encoding            = "UTF-8"
  quote_character     = "\""
  escape_character    = "\\"
  first_row_as_header = true
}

resource "azurerm_data_factory_dataset_delimited_text" "processed_enape" {
  name                = "ds_processed_enape"
  data_factory_id     = azurerm_data_factory.main.id
  linked_service_name = azurerm_data_factory_linked_service_azure_blob_storage.storage.name

  azure_blob_storage_location {
    container = azurerm_storage_container.processed.name
    path      = "enape/latest"
    filename  = "enape.csv"
  }

  column_delimiter    = ","
  row_delimiter       = "\n"
  encoding            = "UTF-8"
  quote_character     = "\""
  escape_character    = "\\"
  first_row_as_header = true
}

resource "azurerm_data_factory_dataset_delimited_text" "rejected_enape" {
  name                = "ds_rejected_enape"
  data_factory_id     = azurerm_data_factory.main.id
  linked_service_name = azurerm_data_factory_linked_service_azure_blob_storage.storage.name

  azure_blob_storage_location {
    container = azurerm_storage_container.raw.name
    path      = "rejected/enape"
  }

  column_delimiter    = ","
  row_delimiter       = "\n"
  encoding            = "UTF-8"
  quote_character     = "\""
  escape_character    = "\\"
  first_row_as_header = true
}

# Mapping Data Flow: reglas de depuración (ver dataflows/clean_enape.dfs)
resource "azurerm_data_factory_data_flow" "clean_enape" {
  name            = "df_clean_enape"
  data_factory_id = azurerm_data_factory.main.id
  description     = "Aplica la cohorte ENAPE 2021, deriva la etiqueta y descarta filas inválidas y duplicadas"

  source {
    name = "RawCsv"
    dataset {
      name = azurerm_data_factory_dataset_delimited_text.raw_enape.name
    }
  }

  transformation {
    name = "SplitRows"
  }

  transformation {
    name = "DeriveFeatures"
  }

  transformation {
    name = "SelectFeatures"
  }

  transformation {
    name = "DistinctRows"
  }

  transformation {
    name = "DropHash"
  }

  sink {
    name = "ProcessedCsv"
    dataset {
      name = azurerm_data_factory_dataset_delimited_text.processed_enape.name
    }
  }

  sink {
    name = "RejectedCsv"
    dataset {
      name = azurerm_data_factory_dataset_delimited_text.rejected_enape.name
    }
  }

  script = file("${path.module}/dataflows/clean_enape.dfs")
}

resource "azurerm_data_factory_pipeline" "clean_enape" {
  name            = "pl_clean_enape"
  data_factory_id = azurerm_data_factory.main.id
  description     = "ETL raw -> processed del dataset ENAPE 2021 (INEGI, México)"

  activities_json = jsonencode([
    {
      name = "CleanEnape"
      type = "ExecuteDataFlow"
      policy = {
        timeout = "0.01:00:00"
        retry   = 0
      }
      typeProperties = {
        dataFlow = {
          referenceName = azurerm_data_factory_data_flow.clean_enape.name
          type          = "DataFlowReference"
        }
        # Mínimo permitido por los Data Flows; se cobra por minuto
        compute = {
          coreCount   = 8
          computeType = "General"
        }
        traceLevel = "Fine"
      }
    }
  ])

  depends_on = [azurerm_role_assignment.adf_blob]
}
