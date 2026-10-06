# Análisis de costos (estimado)

Región `centralus`, precios de pago por uso en USD (referencia de la calculadora
de precios de Azure, septiembre 2026; verificar en
<https://azure.microsoft.com/pricing/calculator/> antes de reportar cifras finales).
La suscripción es **Azure for Students** (USD 100 de crédito anual).

| Recurso | Configuración | Supuesto de uso | Costo mensual aprox. |
|---|---|---|---|
| Azure ML Workspace | Basic | — (sin cargo propio) | USD 0 |
| Compute cluster `cpu-cluster` | Standard_DS3_v2, min 0 / max 4 | ~15 min por entrenamiento (incluye aprovisionamiento), 8 entrenamientos/mes | ≈ USD 0.60 |
| ACI (endpoint) | 1 vCPU, 1.5 GB, Linux | 24/7 (730 h) | ≈ USD 41 |
| ACI (endpoint) | 1 vCPU, 1.5 GB, Linux | Solo horario laboral (≈ 220 h) | ≈ USD 12 |
| Container Registry | Basic (10 GB) | 1 imagen de ~0.8 GB con varias versiones | ≈ USD 5 |
| Storage Account | LRS, Hot | < 1 GB (datos + artefactos MLflow) | < USD 1 |
| Key Vault | Standard | < 10 000 operaciones | < USD 0.10 |
| Log Analytics + App Insights | PerGB2018, retención 30 días | < 1 GB/mes de logs de inferencia | USD 0 – 3 |
| Azure DevOps Pipelines | 1 job hospedado gratuito | < 1 800 min/mes | USD 0 |

**Total estimado:** ≈ USD 20/mes con el endpoint encendido solo en horario laboral,
≈ USD 50/mes con el endpoint 24/7.

## Decisiones que bajan el costo

- **Cluster con `min_instances = 0`**: el cómputo de entrenamiento solo cobra mientras corre un job;
  no hay nodos ociosos.
- **Imagen del endpoint `python:3.12-slim`** en lugar de la imagen `openmpi` de Azure ML
  (≈ 0.8 GB frente a varios GB): menos almacenamiento en ACR y arranques más rápidos de ACI.
- **ACI en lugar de AKS o Managed Online Endpoints**: para el volumen esperado (consultas de
  Bienestar Universitario, decenas por día) un contenedor de 1 vCPU sobra; AKS tendría un costo
  base de nodos de > USD 70/mes.
- **Apagar el ACI fuera de uso** (`az container stop`) durante el semestre académico: es el recurso
  que domina el costo.
- **Retención de logs de 30 días**: suficiente para el monitoreo de drift diario.

## Con el crédito de estudiante

Con USD 100/año, el esquema "endpoint en horario laboral" cubre ~5 meses de operación continua;
para la demostración del curso basta encender el ACI durante las pruebas y la presentación.
