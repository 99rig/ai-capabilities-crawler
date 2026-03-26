import importlib
import logging
import pkgutil
from pathlib import Path

from app.patterns.base import BasePattern

log = logging.getLogger(__name__)

_patterns: list[BasePattern] = []


def discover_patterns() -> list[BasePattern]:
    global _patterns
    if _patterns:
        return _patterns

    package_dir = Path(__file__).parent
    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name in ("base", "registry", "__init__"):
            continue
        try:
            module = importlib.import_module(f"app.patterns.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePattern)
                    and attr is not BasePattern
                    and attr.name
                ):
                    _patterns.append(attr())
                    log.info(f"Registered pattern: {attr.name} ({attr.protocol})")
        except Exception as e:
            log.error(f"Failed to load pattern module {module_name}: {e}")

    return _patterns


def get_patterns() -> list[BasePattern]:
    return _patterns or discover_patterns()
