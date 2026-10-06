"""Gráficas del entrenamiento que se registran como artefactos en MLflow."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin display (cluster de Azure ML / CI)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ml.pipeline.modeling import CLASSES  # noqa: E402


def plot_confusion_matrix(matrix: list[list[int]], path: Path) -> Path:
    """Matriz de confusión con conteos y porcentaje por fila (recall)."""
    cm = np.array(matrix)
    row_pct = cm / cm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(5.2, 4.4), dpi=150)
    ax.imshow(row_pct, cmap="Blues", vmin=0, vmax=1)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            color = "white" if row_pct[i, j] > 0.6 else "#1f2937"
            ax.text(j, i, f"{cm[i, j]}\n{row_pct[i, j]:.0%}", ha="center", va="center",
                    color=color, fontsize=10)
    ax.set_xticks(range(len(CLASSES)), CLASSES)
    ax.set_yticks(range(len(CLASSES)), CLASSES)
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Clase real")
    ax.set_title("Matriz de confusión (test)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_feature_importance(pairs: list[tuple[str, float]], path: Path, top: int = 15) -> Path:
    """Barras horizontales con las `top` features más importantes."""
    pairs = pairs[:top][::-1]
    names = [p[0] for p in pairs]
    values = [p[1] for p in pairs]

    fig, ax = plt.subplots(figsize=(7, 5.2), dpi=150)
    ax.barh(names, values, color="#2563eb")
    ax.set_xlabel("Importancia (reducción media de impureza)")
    ax.set_title(f"Top {top} variables del modelo")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
