"""Sources package - re-export registry and base."""

from client_finder.sources.base import SOURCE_REGISTRY, register_source, BaseSource  # noqa: F401

__all__ = ["SOURCE_REGISTRY", "register_source", "BaseSource"]