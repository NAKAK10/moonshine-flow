"""moonshine-flow package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version

__all__ = ["__version__"]


def _resolve_version() -> str:
    try:
        return package_version("moonshine-flow")
    except PackageNotFoundError:
        return "0.0.0.dev0"


__version__ = _resolve_version()
