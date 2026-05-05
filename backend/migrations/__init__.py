"""Auto-discover migration modules and expose collected list."""
import importlib
import pkgutil
from backend.migrations.runner import Migration


def discover_migrations() -> list[Migration]:
    """Find all v*.py modules in this package and build Migration list."""
    out = []
    for _, modname, _ in pkgutil.iter_modules(__path__):
        if not modname.startswith("v"):
            continue
        if modname == "runner":
            continue
        mod = importlib.import_module(f"backend.migrations.{modname}")
        version = modname[:5]  # 'v0001'
        name = modname[6:] if len(modname) > 5 else modname
        out.append(Migration(version=version, name=name, up=mod.up))
    return sorted(out, key=lambda m: m.version)
