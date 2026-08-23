"""Response schema names must be unique across every app.

Pydantic keys the OpenAPI component map by class name, so two identically
named schema classes in different modules silently collapse into one. The
endpoint that loses is then *documented with the other app's shape*, and
because it is only the schema that is wrong - the JSON on the wire stays
correct - nothing fails until the generated TypeScript client is used
against it.

Convention: every django-ninja response schema is prefixed per-app, e.g.
`HealthSummaryOut`, not `SummaryOut`. This test is the guardrail.
"""

import importlib
import pkgutil

from ninja import Schema

import apps


def _schema_classes():
    """Every ninja Schema subclass declared under `apps.*`, with its module."""
    found: list[tuple[str, str]] = []
    for module_info in pkgutil.walk_packages(apps.__path__, prefix="apps."):
        if module_info.name.endswith(("schemas", "api")) is False:
            continue
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # pragma: no cover - an app without that module
            continue
        for attribute in vars(module).values():
            if (
                isinstance(attribute, type)
                and issubclass(attribute, Schema)
                and attribute is not Schema
                and attribute.__module__ == module_info.name
            ):
                found.append((attribute.__name__, module_info.name))
    return found


def test_no_two_apps_declare_the_same_schema_name():
    seen: dict[str, str] = {}
    clashes: list[str] = []
    for name, module in _schema_classes():
        if name in seen and seen[name] != module:
            clashes.append(f"{name}: {seen[name]} and {module}")
        seen.setdefault(name, module)

    assert not clashes, "schema names collide in the OpenAPI document: " + "; ".join(clashes)
