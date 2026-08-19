"""Adapter registry: which discovery sources are configured and enabled."""

from __future__ import annotations

from config.settings import settings
from discovery.base import DiscoveryAdapter
from discovery.greenhouse import GreenhouseAdapter
from discovery.lever import LeverAdapter

_REGISTRY: dict[str, type[DiscoveryAdapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
}


def enabled_sources() -> list[str]:
    """Return adapter names that have at least one configured target."""

    sources: list[str] = []
    if settings.greenhouse_company_list:
        sources.append("greenhouse")
    if settings.lever_company_list:
        sources.append("lever")
    return sources


def get_adapter(name: str) -> DiscoveryAdapter:
    """Instantiate an adapter by name."""

    try:
        adapter_cls = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown discovery source: {name}") from exc
    return adapter_cls()


def registered_sources() -> list[str]:
    """All known adapter names, whether or not they are configured."""

    return sorted(_REGISTRY.keys())
