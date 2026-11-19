terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      # purge_protection está activo en el Key Vault: no intentar purgar al destruir
      purge_soft_deleted_secrets_on_destroy = false
    }
    resource_group {
      # Application Insights crea por su cuenta el action group
      # "Application Insights Smart Detection" dentro del resource group.
      # Terraform no lo gestiona, así que al destruir el RG el borrado falla
      # con "the Resource Group still contains Resources". Con esta bandera
      # se elimina el RG completo y Azure limpia lo que quede dentro.
      prevent_deletion_if_contains_resources = false
    }
  }
}
