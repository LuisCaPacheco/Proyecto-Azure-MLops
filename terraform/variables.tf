variable "location" {
  description = "Región de Azure donde se desplegará la infraestructura"
  type        = string
  default     = "centralus"
}

variable "project_name" {
  description = "Nombre corto del proyecto, se usa como prefijo de los recursos (debe ser único global)"
  type        = string
  default     = "mlopsproj"
}

variable "environment" {
  description = "Entorno de despliegue"
  type        = string
  default     = "dev"
}

variable "compute_vm_size" {
  description = "Tamaño de VM del compute cluster de entrenamiento"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "compute_min_nodes" {
  description = "Número mínimo de nodos del compute cluster"
  type        = number
  default     = 0
}

variable "compute_max_nodes" {
  description = "Número máximo de nodos del compute cluster"
  type        = number
  default     = 4
}

variable "aci_cpu" {
  description = "CPU (vCores) de la instancia de inferencia ACI"
  type        = number
  default     = 1
}

variable "aci_memory" {
  description = "Memoria (GB) de la instancia de inferencia ACI"
  type        = number
  default     = 1.5
}

variable "baseline_accuracy" {
  description = "Accuracy mínimo que debe superar un modelo para ser promovido"
  type        = number
  default     = 0.75
}
