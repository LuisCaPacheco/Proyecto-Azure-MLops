# Estado remoto de Terraform en Azure Blob Storage (compartido por el equipo
# y por el pipeline, con bloqueo de estado).
#
# La cuenta de almacenamiento del estado vive fuera de este código para no
# depender de sí misma; se crea una sola vez con scripts/bootstrap_tfstate.sh.
# Los valores se pasan en `terraform init`:
#
#   cp backend.hcl.example backend.hcl   # y ajustar los nombres
#   terraform init -backend-config=backend.hcl
#
# Si ya existe un estado local (terraform.tfstate), migrarlo:
#   terraform init -backend-config=backend.hcl -migrate-state
terraform {
  backend "azurerm" {}
}
