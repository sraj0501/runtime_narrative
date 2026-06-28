from __future__ import annotations

import functools
import inspect
import sys
from types import ModuleType
from typing import Sequence

_SKIP_ATTR = "_narrative_skip"
_STAGE_NAME_ATTR = "_narrative_stage_name"


def no_stage(fn):
    """Mark a callable to be skipped by all auto-instrumentation helpers.

    Apply before ``@narrative_class`` or ``instrument_module`` to exclude a
    specific method or function from stage wrapping:

        @narrative_class
        class OrderService:
            def charge(self, order): ...

            @no_stage
            def _internal_helper(self): ...   # not wrapped
    """
    fn._narrative_skip = True
    return fn


def _is_instrumentable(name: str, obj: object) -> bool:
    if name.startswith("_"):
        return False
    if getattr(obj, _SKIP_ATTR, False):
        return False
    return True


def _wrap_as_stage(fn, stage_name: str):
    """Return *fn* wrapped in a sync or async ``stage()`` context."""
    from .stage import stage as _stage

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            async with _stage(stage_name):
                return await fn(*args, **kwargs)
        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*args, **kwargs):
        with _stage(stage_name):
            return fn(*args, **kwargs)
    return _sync_wrapper


def narrative_stage(name: str | None = None):
    """Per-method stage decorator for explicit naming.

    Works both standalone and as an override inside ``@narrative_class``.
    When used inside ``@narrative_class``, the custom name takes precedence
    over the default ``ClassName.method_name`` and the method is not
    double-wrapped.

    Standalone::

        @narrative_stage("Process Order")
        def process(order): ...   # stage name: "Process Order"

    Inside ``@narrative_class``::

        @narrative_class
        class OrderService:
            @narrative_stage("Validate Order")
            def validate(self, order): ...   # stage name: "Validate Order"

            def charge(self, order): ...     # stage name: "OrderService.charge"
    """
    def decorator(fn):
        stage_name = name or fn.__name__.replace("_", " ").strip().title()
        wrapped = _wrap_as_stage(fn, stage_name)
        setattr(wrapped, _STAGE_NAME_ATTR, stage_name)
        return wrapped
    return decorator


def narrative_class(
    _cls=None,
    *,
    instrument_classmethods: bool = False,
    instrument_staticmethods: bool = False,
):
    """Class decorator — every public instance method becomes a stage.

    The stage name is ``ClassName.method_name``.  Methods decorated with
    ``@narrative_stage("name")`` keep their custom name and are not
    re-wrapped.  Private methods (names starting with ``_``),
    ``@no_stage``-marked methods, and ``property`` descriptors are left
    untouched.  ``classmethod`` and ``staticmethod`` are skipped unless
    ``instrument_classmethods=True`` / ``instrument_staticmethods=True``.

        @narrative_class
        class OrderService:
            def validate(self, order): ...          # → "OrderService.validate"

            @narrative_stage("Charge Customer")
            def charge(self, order): ...            # → "Charge Customer"

            @no_stage
            def _log(self, msg): ...                # not wrapped

        @narrative_class(instrument_classmethods=True)
        class Factory:
            @classmethod
            def create(cls, **kw): ...              # → "Factory.create"
    """

    def _apply(cls):
        for name, value in list(vars(cls).items()):
            if not _is_instrumentable(name, value):
                continue

            if isinstance(value, classmethod):
                if instrument_classmethods:
                    fn = value.__func__
                    if not getattr(fn, _SKIP_ATTR, False) and not hasattr(fn, _STAGE_NAME_ATTR):
                        setattr(cls, name, classmethod(_wrap_as_stage(fn, f"{cls.__name__}.{name}")))
                continue

            if isinstance(value, staticmethod):
                if instrument_staticmethods:
                    fn = value.__func__
                    if not getattr(fn, _SKIP_ATTR, False) and not hasattr(fn, _STAGE_NAME_ATTR):
                        setattr(cls, name, staticmethod(_wrap_as_stage(fn, f"{cls.__name__}.{name}")))
                continue

            if isinstance(value, property):
                continue

            if not inspect.isfunction(value):
                continue

            # Already wrapped by @narrative_stage — honour its custom name.
            if hasattr(value, _STAGE_NAME_ATTR):
                continue

            setattr(cls, name, _wrap_as_stage(value, f"{cls.__name__}.{name}"))
        return cls

    if _cls is not None:
        # Called as @narrative_class (no parentheses)
        return _apply(_cls)
    # Called as @narrative_class(...) with keyword arguments
    return _apply


def instrument_module(module: ModuleType) -> None:
    """Wrap all public callables *defined in* ``module`` as stages, in-place.

    - Classes whose ``__module__`` matches the module get ``@narrative_class``
      applied.
    - Top-level functions whose ``__module__`` matches get wrapped directly;
      the stage name is the function name.
    - Symbols imported from other modules are not touched.

        import runtime_narrative
        runtime_narrative.instrument_module(myapp.services)
    """
    module_name = getattr(module, "__name__", None)
    for name in list(vars(module).keys()):
        if not _is_instrumentable(name, None):
            continue
        obj = getattr(module, name, None)
        if obj is None:
            continue
        if not _is_instrumentable(name, obj):
            continue
        if inspect.isclass(obj):
            if getattr(obj, "__module__", None) == module_name:
                narrative_class(obj)
        elif inspect.isfunction(obj):
            if getattr(obj, "__module__", None) == module_name:
                setattr(module, name, _wrap_as_stage(obj, name))


class _NarrativeLoader:
    """importlib loader wrapper that calls ``instrument_module`` after exec."""

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped

    def create_module(self, spec):
        cm = getattr(self._wrapped, "create_module", None)
        return cm(spec) if cm is not None else None

    def exec_module(self, module: ModuleType) -> None:
        self._wrapped.exec_module(module)
        try:
            instrument_module(module)
        except Exception:
            # Never let instrumentation failure prevent a successful import.
            pass


class _NarrativeFinder:
    """sys.meta_path finder that auto-instruments app modules on import."""

    def __init__(self, roots: tuple[str, ...]) -> None:
        self._roots = roots

    def find_spec(self, fullname: str, path, target=None):
        import importlib.util

        # Temporarily remove ourselves to avoid infinite recursion.
        try:
            idx = sys.meta_path.index(self)
            sys.meta_path.pop(idx)
        except ValueError:
            return None

        try:
            spec = importlib.util.find_spec(fullname)
        except Exception:
            spec = None
        finally:
            sys.meta_path.insert(idx, self)

        if spec is None or spec.origin is None or spec.loader is None:
            return None
        if not any(spec.origin.startswith(r) for r in self._roots):
            return None
        spec.loader = _NarrativeLoader(spec.loader)
        return spec


def auto_instrument(*, app_roots: Sequence[str] | None = None) -> _NarrativeFinder:
    """Register an import hook that instruments app modules automatically.

    Only modules whose source file starts with one of ``app_roots`` (default:
    current working directory) are instrumented — stdlib and installed packages
    are unaffected.  Returns the ``_NarrativeFinder`` so it can be removed via
    ``sys.meta_path.remove(finder)`` when no longer needed.

        # Entry point only — instruments everything imported after this line:
        import runtime_narrative
        runtime_narrative.auto_instrument()
    """
    import os
    roots = tuple(
        os.path.abspath(os.path.expanduser(str(r)))
        for r in (app_roots or [os.getcwd()])
    )
    finder = _NarrativeFinder(roots)
    sys.meta_path.insert(0, finder)
    return finder
