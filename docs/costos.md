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
| Azure Data Factory | Data Flow, 8 vCores General | ~8 min por corrida (incluye arranque del cluster Spark), 8 corridas/mes | ≈ USD 2 – 3 (estimado, verificar) |
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

## Cómputo de entrenamiento (CPU vs GPU) frente a costo de inferencia

### Entrenamiento: CPU vs GPU

Precios por hora de referencia (pago por uso, Linux; **verificar en la calculadora antes de
reportarlos**). El costo por entrenamiento asume un job de ~15 min, que es casi todo
aprovisionamiento del nodo y preparación del entorno: el ajuste del modelo final
(RandomForest de 300 árboles sobre 3539 filas) tarda ~1 s medido en local con 12 núcleos, y
unos pocos segundos en los 4 vCPU de un DS3_v2.

| VM | Tipo | USD/h aprox. | Costo por entrenamiento (15 min) | 8 entrenamientos/mes |
|---|---|---|---|---|
| Standard_DS3_v2 (4 vCPU, 14 GB) | CPU — **la que usa el proyecto** | 0.29 | ≈ 0.07 | ≈ 0.60 |
| Standard_DS3_v2 low priority | CPU interrumpible | ≈ 0.06 | ≈ 0.015 | ≈ 0.12 |
| Standard_NC4as_T4_v3 (1 × T4) | GPU | ≈ 0.53 | ≈ 0.13 | ≈ 1.05 |
| Standard_NC6s_v3 (1 × V100) | GPU | ≈ 3.06 | ≈ 0.77 | ≈ 6.10 |

**Conclusión: GPU no se justifica.** scikit-learn entrena RandomForest solo en CPU, así que una
VM con GPU costaría entre 2 y 10 veces más por hora sin reducir el tiempo; la GPU quedaría
ociosa. Solo tendría sentido si el modelo migrara a redes neuronales o a XGBoost/LightGBM con
soporte GPU y un dataset varios órdenes de magnitud mayor. Para bajar aún más el costo, la
opción correcta es `compute_vm_priority = "LowPriority"` (variable de Terraform), no GPU.

### Inferencia

ACI cobra por segundo que el contenedor está encendido, atienda o no solicitudes, así que el
costo por predicción depende del volumen:

| Volumen | ACI 24/7 (≈ USD 41/mes) | ACI en horario laboral (≈ USD 12/mes) |
|---|---|---|
| 100 predicciones/día (3 000/mes) | ≈ USD 13.70 por 1 000 | ≈ USD 4.00 por 1 000 |
| 1 000 predicciones/día (30 000/mes) | ≈ USD 1.37 por 1 000 | ≈ USD 0.40 por 1 000 |
| 10 000 predicciones/día (300 000/mes) | ≈ USD 0.14 por 1 000 | ≈ USD 0.04 por 1 000 |

La capacidad no es el límite: una predicción individual tarda ~75 ms y un lote de 500
estudiantes ~100 ms (medido en local; la latencia real en 1 vCPU de ACI se lee en el workbook
de Azure Monitor, percentiles P50/P95/P99). Por eso, para evaluar una cohorte completa conviene
`/predict/batch` y no cientos de llamadas a `/predict`.

### Comparación

| | Entrenamiento (DS3_v2) | Inferencia (ACI) |
|---|---|---|
| Modelo de cobro | por minuto de job; 0 nodos en reposo | por segundo encendido, con o sin tráfico |
| Costo mensual | ≈ USD 0.60 (8 jobs) | ≈ USD 12 – 41 |
| Equivalencia | 1 entrenamiento ≈ 1.3 h de endpoint encendido | 1 mes 24/7 ≈ 560 entrenamientos |

El cómputo de inferencia es más del 95 % del gasto de cómputo de la plataforma: el modelo se
entrena pocas veces y en segundos, pero el endpoint debe estar disponible. Las decisiones de
ahorro que importan están en la inferencia (apagar el ACI fuera de horario, usar lotes), no en
el entrenamiento.
