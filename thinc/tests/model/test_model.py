import pytest
import threading
import time
from thinc.api import Linear, NumpyOps, get_current_ops, use_device, Model
import numpy

from ..util import make_tempdir


@pytest.fixture
def model_with_no_args():
    return Linear()


def create_model(name):
    return Model(name, lambda X: (X, lambda dY: dY))


def test_model_defaults_to_cpu(model_with_no_args):
    assert isinstance(model_with_no_args.ops, NumpyOps)


def test_models_get_different_ids(model_with_no_args):
    model1 = Linear()
    model2 = Linear()
    assert model1.id != model2.id


def test_init_assigns_attributes():
    model = Linear()
    model._mem
    assert model.layers == []


def test_model_init():
    model_a = create_model("a")
    model = Model(
        "test",
        lambda X: (X, lambda dY: dY),
        dims={"nI": 10, "nO": None},
        params={"W": numpy.zeros((10,)), "b": None},
        grads={"W": numpy.zeros((10,)), "b": None},
        refs={"a": model_a, "b": None},
        attrs={"foo": "bar"},
    )
    model.layers.append(model_a)
    assert model.has_param("W")
    assert model.get_param("W").shape == (10,)
    assert model.has_param("b") is None
    with pytest.raises(KeyError):
        model.get_param("b")
    with pytest.raises(KeyError):
        model.get_param("X")
    model.set_param("X", numpy.zeros((10,)))
    assert model.has_param("X")
    assert model.get_param("X").shape == (10,)
    assert model.has_grad("W") is None
    assert model.get_grad("W").shape == (10,)
    assert not model.has_grad("xyz")
    with pytest.raises(KeyError):
        model.get_grad("b")
    assert model.has_grad("W") is None
    model.set_param("W", model.ops.alloc_f1d(10))
    model.set_grad("W", model.ops.alloc_f1d(10))
    assert model.has_dim("nI")
    assert model.get_dim("nI") == 10
    with pytest.raises(KeyError):
        model.get_dim("xyz")
    with pytest.raises(ValueError):
        model.get_dim("nO")
    with pytest.raises(KeyError):
        model.set_dim("xyz", 20)
    assert model.has_ref("a")
    assert model.get_ref("a").name == "a"
    assert not model.has_ref("xyz")
    with pytest.raises(KeyError):
        model.get_ref("xyz")
    assert model.has_ref("b") is None
    with pytest.raises(ValueError):
        model.get_ref("b")
    model.set_ref("c", model_a)
    assert model.has_ref("c")
    assert model.get_ref("c").name == "a"
    with pytest.raises(ValueError):
        model.set_ref("c", create_model("c"))
    assert model.has_attr("foo")
    assert not model.has_attr("bar")
    assert model.get_attr("foo") == "bar"
    with pytest.raises(KeyError):
        model.get_attr("bar")
    model.set_attr("bar", "baz")
    assert model.has_attr("bar")


def test_param_names():
    model = create_model("tmp")
    assert model.param_names == tuple()
    model.set_param("param1", None)
    assert model.param_names == ("param1",)
    model.set_param("param2", None)
    assert model.param_names == ("param1", "param2")


def test_grad_names():
    model = create_model("tmp")
    assert model.grad_names == tuple()
    model.set_param("param1", model.ops.alloc_f2d(4, 4))
    model.set_grad("param1", model.ops.alloc_f2d(4, 4) + 1)
    assert model.grad_names == ("param1",)


def test_dim_names():
    model = Linear(5, 3)
    assert model.dim_names == ("nO", "nI")


def test_attr_names():
    model = Linear(5, 3)
    assert model.attr_names == tuple()
    model.set_attr("hello", "world")
    assert model.attr_names == ("hello",)


def test_model_set_reference():
    parent = create_model("parent")
    child = create_model("child")
    grandchild = create_model("child")
    parent.layers.append(child)
    assert parent.ref_names == tuple()
    parent.set_ref("kid", child)
    assert parent.ref_names == ("kid",)
    assert parent.get_ref("kid") is child
    child.layers.append(grandchild)
    with pytest.raises(KeyError):
        parent.get_ref("grandkid")
    parent.set_ref("grandkid", grandchild)
    assert parent.get_ref("grandkid") is grandchild
    parent.remove_node(grandchild)
    assert grandchild not in child.layers
    assert not parent.has_ref("grandkind")


def test_use_device():
    class_ops = get_current_ops()
    dev_id = id(class_ops)
    with use_device(class_ops.device):
        new_ops = get_current_ops()
        assert id(new_ops) == dev_id
    with use_device("gpu"):
        new_ops = get_current_ops()
        assert id(new_ops) != dev_id
    new_ops = get_current_ops()
    assert id(new_ops) == dev_id


def test_model_can_save_to_disk(model_with_no_args):
    with make_tempdir() as path:
        model_with_no_args.to_disk(path / "thinc_model")


def test_model_can_load_from_disk(model_with_no_args):
    with make_tempdir() as path:
        model_with_no_args.to_disk(path / "thinc_model")
        m2 = model_with_no_args.from_disk(path / "thinc_model")
    assert model_with_no_args.to_bytes() == m2.to_bytes()


def test_bind_plus():
    with Model.define_operators({"+": lambda a, b: (a.name, b.name)}):
        m = create_model(name="a") + create_model(name="b")
        assert m == ("a", "b")


def test_plus_chain():
    with Model.define_operators({"+": lambda a, b: a}):
        m = (
            create_model(name="a")
            + create_model(name="b")
            + create_model(name="c")
            + create_model(name="d")
        )
        assert m.name == "a"


# TODO: This currently causes a n AttributeError in the first thread. The error
# isn't raised in the test (because threading) but it's written to stdout.
@pytest.mark.skip(reason="need to fix error")
def test_overload_operators_in_subthread():
    """Test we can create a model in a child thread with overloaded operators."""
    # Worker1 will start and run, while worker 2 sleeps after Model.define_operators.
    # Without thread-safety, worker2 will find that its operator definitions
    # have been removed, causing an error.
    worker1 = threading.Thread(target=_overload_plus, args=("+", 0))
    worker2 = threading.Thread(target=_overload_plus, args=("*", 1))
    worker2.start()
    worker1.start()
    worker1.join()
    worker2.join()

    worker1 = threading.Thread(target=_overload_plus, args=("+", 1))
    worker2 = threading.Thread(target=_overload_plus, args=("*", 0))
    worker2.start()
    worker1.start()
    worker1.join()
    worker2.join()


def _overload_plus(operator, sleep):
    m1 = create_model(name="a")
    m2 = create_model(name="b")
    with Model.define_operators({operator: lambda a, b: a.name + b.name}):
        time.sleep(sleep)
        if operator == "+":
            value = m1 + m2
        else:
            value = m1 * m2
    assert value == "ab"
    assert Model._thread_local.operators == {}


def test_nested_operator_contexts():
    m1 = create_model(name="a")
    m2 = create_model(name="b")
    assert Model._thread_local.operators == {}
    with Model.define_operators({"+": lambda a, b: a.name + b.name}):
        value = m1 + m2
        with pytest.raises(TypeError):
            value = m1 * m2
        with Model.define_operators({"*": lambda a, b: a.name + b.name}):
            with pytest.raises(TypeError):
                value = m1 + m2
            value = m1 * m2
            with Model.define_operators({"-": lambda a, b: a.name + b.name}):
                with pytest.raises(TypeError):
                    value = m1 + m2
                value = m1 - m2
            with pytest.raises(TypeError):
                value = m1 + m2
            value = m1 * m2
        value = m1 + m2
        with pytest.raises(TypeError):
            value = m1 * m2
    assert value == "ab"
    assert Model._thread_local.operators == {}


@pytest.mark.parametrize("op", "+ - * @ / // % ** << >> & ^ |".split())
def test_all_operators(op):
    m1 = Linear()
    m2 = Linear()
    with Model.define_operators({op: lambda a, b: a.name + b.name}):
        if op == "+":
            value = m1 + m2
        else:
            with pytest.raises(TypeError):
                value = m1 + m2
        if op == "-":
            value = m1 - m2
        else:
            with pytest.raises(TypeError):
                value = m1 - m2

        if op == "*":
            value = m1 * m2
        else:
            with pytest.raises(TypeError):
                value = m1 * m2

        if op == "@":
            value = m1.__matmul__(m2)  # Be kind to Python 2...
        else:
            with pytest.raises(TypeError):
                value = m1.__matmul__(m2)

        if op == "/":
            value = m1 / m2
        else:
            with pytest.raises(TypeError):
                value = m1 / m2

        if op == "//":
            value = m1 // m2
        else:
            with pytest.raises(TypeError):
                value = m1 // m2
        if op == "^":
            value = m1 ^ m2
        else:
            with pytest.raises(TypeError):
                value = m1 ^ m2
        if op == "%":
            value = m1 % m2
        else:
            with pytest.raises(TypeError):
                value = m1 % m2
        if op == "**":
            value = m1 ** m2
        else:
            with pytest.raises(TypeError):
                value = m1 ** m2
        if op == "<<":
            value = m1 << m2
        else:
            with pytest.raises(TypeError):
                value = m1 << m2
        if op == ">>":
            value = m1 >> m2
        else:
            with pytest.raises(TypeError):
                value = m1 >> m2
        if op == "&":
            value = m1 & m2
        else:
            with pytest.raises(TypeError):
                value = m1 & m2
        if op == "^":
            value = m1 ^ m2
        else:
            with pytest.raises(TypeError):
                value = m1 ^ m2
        if op == "|":
            value = m1 | m2
        else:
            with pytest.raises(TypeError):
                value = m1 | m2  # noqa: F841
    assert Model._thread_local.operators == {}