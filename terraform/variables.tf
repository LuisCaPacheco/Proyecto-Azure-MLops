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
  default     = 0.70
}

variable "deploy_aci" {
  description = "Crear el endpoint de inferencia en ACI (requiere la imagen en ACR)"
  type        = bool
  default     = false
}

variable "endpoint_image_tag" {
  description = "Tag de la imagen acr.../endpoint a desplegar"
  type        = string
  default     = "latest"
}

variable "rate_limit_per_min" {
  description = "Solicitudes por minuto permitidas por IP en el endpoint"
  type        = number
  default     = 60
}

variable "alert_emails" {
  description = "Correos que reciben las alertas de Azure Monitor"
  type        = list(string)
  default     = []
}

variable "data_scientist_object_ids" {
  description = "Object IDs de Azure AD con rol AzureML Data Scientist (entrenan/registran)"
  type        = list(string)
  default     = []
}

variable "reader_object_ids" {
  description = "Object IDs de Azure AD con rol Reader (solo consultan métricas)"
  type        = list(string)
  default     = []
}
