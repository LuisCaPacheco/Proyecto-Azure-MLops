# Proyecto_Azure_MLOps
## P07 - Plataforma MLOps: Entrenamiento e Inferencia de Modelos en Azure

Reto académico avanzado (8 semanas). Plataforma MLOps end-to-end sobre Microsoft Azure
con Terraform (infraestructura) y Azure Pipelines (CI/CD).

## Arquitectura

```
CSV/JSON ──► Azure Blob Storage ──► Azure ML (Compute + MLflow + Model Registry)
                  │                        │
            Azure Data Factory             │ mejor modelo
                  │                        ▼
                  │                Model Packaging (Docker → ACR)
                  ▼                        │
        Azure Monitor ◄──────────────── ACI Endpoint (REST /predict)
```

## Estructura del repositorio

```
Proyecto_Azure_MLOps/
├── terraform/            # Infraestructura como código (Sem 1-2)
├── ml/
│   ├── data/             # Datasets
│   ├── pipeline/         # Scripts de entrenamiento/evaluación (Sem 3-4)
│   └── tests/            # Tests unitarios
├── endpoint/             # Dockerfile + FastAPI de inferencia (Sem 5-6)
├── .azure-pipelines/     # Pipeline MLOps CI/CD (Sem 7-8)
└── docs/                 # Documentación, informe MLflow, costos
```

## Estado del proyecto

| Fase | Semanas | Entregable | Estado |
|------|---------|-----------|--------|
| 1. Infraestructura Base | 1-2 | Terraform: Workspace, Storage, ACR, Key Vault, Compute | ✅ Código creado |
| 2. Pipeline Datos + Train | 3-4 | Dataset, entrenamiento, MLflow, Model Registry | ⏳ Pendiente |
| 3. Packaging + Inferencia | 5-6 | Docker, ACR push, ACI deploy, endpoint /predict | ⏳ Pendiente |
| 4. CI/CD + Monitoreo | 7-8 | Azure Pipelines MLOps, data drift, docs | ⏳ Pendiente |

## Criterios de evaluación

- Infraestructura Terraform desplegada (20%)
- Pipeline entrenamiento con MLflow (20%)
- Model Registry con promoción (15%)
- Endpoint inferencia en ACI (20%)
- Pipeline CI/CD MLOps (15%)
- Monitoreo, documentación y costos (10%)
