from typing import Tuple, Callable, List, Optional

from .base import Model, Array


def chain(*layers: List[Model]) -> Model:
    return Model(
        ">>".join(layer.name for layer in layers),
        forward,
        init=init,
        dims={"nO": None, "nI": None},
        layers=layers,
        attrs={},
    )


def forward(model: Model, X: Array, is_train: bool) -> Tuple[Array, Callable]:
    """Apply the layers of `model` in sequence, feeding the output from one
    layer into the next.

    Returns (tuple):
        The output of the model, and a callback to complete the backward pass.
    """
    callbacks = []
    for layer in model.layers:
        X, inc_layer_grad = layer(X, is_train=is_train)
        callbacks.append(inc_layer_grad)

    def backprop(gradient: Array) -> Array:
        for callback in reversed(callbacks):
            gradient = callback(gradient)
        return gradient

    return X, backprop


def init(model: Model, X: Optional[Array] = None, Y: Optional[Array] = None) -> None:
    if not model.layers:
        return
    if Y is not None:
        model.layers[-1].initialize(X=None, Y=Y)
    for layer in model.layers:
        layer.initialize(X=X)
        X = layer.predict(X)
    model.set_dim("nI", model.layers[0].get_dim("nI"))
    model.set_dim("nO", model.layers[-1].get_dim("nO"))