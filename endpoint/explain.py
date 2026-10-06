"""Explicabilidad local del RandomForest (descomposición de contribuciones).

Para cada árbol se recorre el camino de decisión del estudiante: cada split
cambia la distribución de clases del nodo, y ese cambio se atribuye a la
variable del split (método de Saabas, el mismo principio que TreeSHAP en su
versión aproximada). Promediando sobre los árboles se cumple exactamente:

    predict_proba(x) = base + sum(contribuciones de cada variable)

Así se sabe qué variables empujaron a un estudiante hacia "Dropout" sin
añadir dependencias pesadas (shap/numba) a la imagen del endpoint.
"""

import numpy as np


def _node_distributions(tree) -> np.ndarray:
    """Distribución de clases normalizada de cada nodo del árbol."""
    values = tree.value[:, 0, :].astype(float)
    return values / values.sum(axis=1, keepdims=True)


def contributions(model, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (base, contrib) para una sola fila `x` de shape (n_features,).

    base:    (n_classes,) distribución media en la raíz de los árboles.
    contrib: (n_features, n_classes) aporte de cada variable a cada clase.
    """
    x = np.asarray(x, dtype=np.float32).reshape(1, -1)
    n_features = x.shape[1]
    n_classes = len(model.classes_)
    base = np.zeros(n_classes)
    contrib = np.zeros((n_features, n_classes))

    for est in model.estimators_:
        tree = est.tree_
        dist = _node_distributions(tree)
        path = est.decision_path(x).indices  # nodos visitados, de raíz a hoja
        base += dist[path[0]]
        for parent, child in zip(path[:-1], path[1:]):
            contrib[tree.feature[parent]] += dist[child] - dist[parent]

    n_trees = len(model.estimators_)
    return base / n_trees, contrib / n_trees


def explain(model, x, feature_names: list[str], class_names: list[str],
            target_class: str, top: int = 8) -> dict:
    """Top variables que suben/bajan la probabilidad de `target_class`."""
    base, contrib = contributions(model, x)
    k = class_names.index(target_class)
    order = np.argsort(-np.abs(contrib[:, k]))[:top]
    values = np.asarray(x, dtype=float).ravel()
    return {
        "target_class": target_class,
        "base_probability": round(float(base[k]), 4),
        "predicted_probability": round(float(base[k] + contrib[:, k].sum()), 4),
        "top_factors": [
            {
                "feature": feature_names[i],
                "value": float(values[i]),
                "contribution": round(float(contrib[i, k]), 4),
                "effect": "aumenta" if contrib[i, k] > 0 else "reduce",
            }
            for i in order
        ],
    }
