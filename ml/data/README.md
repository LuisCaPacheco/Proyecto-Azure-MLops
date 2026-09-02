# Datos

Este directorio contiene el dataset de clasificación **Iris** (UCI ML Repository / scikit-learn).

- `iris.csv` → versión local en CSV (generada por `ml/pipeline/load_data.py` desde `sklearn.datasets.load_iris`).
- En producción, los datos se ingieren desde Azure Blob Storage (`raw` / `processed`).

Los CSV están en `.gitignore` (ver raíz) a excepción de este README y `.gitkeep`.
