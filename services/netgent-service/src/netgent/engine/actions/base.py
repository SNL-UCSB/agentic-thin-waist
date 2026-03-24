from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class ActionMeta(type):
    """Metaclass that keeps a registry of all concrete actions."""

    _registry: dict[str, type["Action"]] = {}

    def __new__(
        mcls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
    ) -> "ActionMeta":
        cls = super().__new__(mcls, name, bases, namespace)

        if namespace.get("__abstract__", False):
            return cls

        action_name = namespace.get("action_name") or name
        docs = namespace.get("docs") or inspect.getdoc(cls) or ""

        existing = mcls._registry.get(action_name)
        if existing is not None and existing is not cls:
            raise ValueError(f"Action '{action_name}' is already registered")

        cls.action_name = action_name
        cls.docs = docs
        mcls._registry[action_name] = cls
        return cls

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        return cls.run(*args, **kwargs)

    @classmethod
    def get_registry(mcls) -> dict[str, type["Action"]]:
        return dict(mcls._registry)

    @classmethod
    def get_action(mcls, name: str) -> type["Action"]:
        try:
            return mcls._registry[name]
        except KeyError as exc:
            raise KeyError(f"Unknown action '{name}'") from exc


class Action(metaclass=ActionMeta):
    """Base type for all NetGent actions."""

    __abstract__ = True

    action_name: ClassVar[str]
    docs: ClassVar[str]
    signature: ClassVar[inspect.Signature]
    __wrapped__: ClassVar[Callable[..., Any]]

    @classmethod
    def run(cls, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{cls.__name__}.run() must be implemented")

    @classmethod
    async def arun(cls, *args: Any, **kwargs: Any) -> Any:
        result = cls.run(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def action(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
) -> Callable[[Callable[P, R]], type[Action]] | type[Action]:
    """Create a registered Action class from a plain function.

    Example:
        @action
        def open_url(url: str) -> str:
            return f"Opened {url}"
    """

    def decorator(fn: Callable[P, R]) -> type[Action]:
        resolved_name = name or fn.__name__
        resolved_docs = inspect.getdoc(fn) or ""
        resolved_signature = inspect.signature(fn)

        def run(cls: type[Action], *args: P.args, **kwargs: P.kwargs) -> R:
            return fn(*args, **kwargs)

        action_cls = ActionMeta(
            fn.__name__,
            (Action,),
            {
                "__module__": fn.__module__,
                "__doc__": fn.__doc__,
                "__qualname__": fn.__qualname__,
                "__wrapped__": fn,
                "__signature__": resolved_signature,
                "action_name": resolved_name,
                "docs": resolved_docs,
                "signature": resolved_signature,
                "run": classmethod(run),
            },
        )
        return action_cls

    if func is None:
        return decorator
    return decorator(func)


def get_action(name: str) -> type[Action]:
    return ActionMeta.get_action(name)


def list_actions() -> dict[str, type[Action]]:
    return ActionMeta.get_registry()
