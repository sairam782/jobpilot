"""Adapter registry: enumerate and instantiate discovery sources."""

from __future__ import annotations

from collections.abc import Callable

from discovery.adzuna import AdzunaAdapter
from discovery.ashby import AshbyAdapter
from discovery.base import DiscoveryAdapter
from discovery.greenhouse import GreenhouseAdapter
from discovery.jooble import JoobleAdapter
from discovery.lever import LeverAdapter
from discovery.remoteok import RemoteOKAdapter
from discovery.remotive import RemotiveAdapter
from discovery.smartrecruiters import SmartRecruitersAdapter
from discovery.themuse import TheMuseAdapter
from discovery.usajobs import USAJobsAdapter
from discovery.workable import WorkableAdapter

_REGISTRY: dict[str, Callable[[], DiscoveryAdapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "workable": WorkableAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "themuse": TheMuseAdapter,
    "remoteok": RemoteOKAdapter,
    "remotive": RemotiveAdapter,
    "usajobs": USAJobsAdapter,
    "adzuna": AdzunaAdapter,
    "jooble": JoobleAdapter,
}


def registered_sources() -> list[str]:
    """All known adapter names, in a stable order."""

    return list(_REGISTRY.keys())


def get_adapter(name: str) -> DiscoveryAdapter:
    """Instantiate an adapter by name (may return a disabled instance)."""

    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown discovery source: {name}") from exc
    return factory()


def enabled_sources() -> list[str]:
    """Adapter names whose runtime prerequisites (keys / company lists) are satisfied."""

    return [name for name, factory in _REGISTRY.items() if factory().enabled()]


def all_adapters() -> list[DiscoveryAdapter]:
    """Instantiate every registered adapter (enabled or not)."""

    return [factory() for factory in _REGISTRY.values()]


def enabled_adapters(only: list[str] | None = None) -> list[DiscoveryAdapter]:
    """Return live adapters, optionally narrowed to a caller-provided subset."""

    result: list[DiscoveryAdapter] = []
    for name, factory in _REGISTRY.items():
        if only and name not in only:
            continue
        adapter = factory()
        if adapter.enabled():
            result.append(adapter)
    return result
