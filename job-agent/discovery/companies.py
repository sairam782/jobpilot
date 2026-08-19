"""Curated per-ATS company packs for AI / ML / DS / adjacent hiring.

Per-company ATS adapters (Greenhouse, Lever, Ashby, Workable) have no
cross-company search. They need a list of company slugs. Rather than
force every operator to research 100 slugs manually, we ship curated
packs organized by domain.

Packs are additive: enable one via ``GREENHOUSE_PACKS=ai-labs,healthcare-ai``
in ``.env`` and the corresponding slugs are folded into
``GREENHOUSE_COMPANIES`` at runtime.

**These lists are maintained by hand and will drift over time.** They
are a "warm start", not authoritative — add companies you actually
care about via the plain ``*_COMPANIES`` env vars.

Only companies whose board_url follows the standard shape are listed:
    Greenhouse:  https://boards.greenhouse.io/<slug>
    Lever:       https://jobs.lever.co/<slug>
    Ashby:       https://jobs.ashbyhq.com/<slug>
    Workable:    https://apply.workable.com/<slug>
"""

from __future__ import annotations

# ---------- Greenhouse ------------------------------------------------------

GREENHOUSE_PACKS: dict[str, list[str]] = {
    "ai-labs": [
        "openai", "anthropic", "cohere", "adeptailabs", "runwayml",
        "elevenlabs", "mistralai", "stabilityai", "characterai",
        "perplexityai", "inflectionai",
    ],
    "big-tech-ai": [
        # Well-known AI/ML-heavy engineering orgs that use Greenhouse
        "airbnb", "stripe", "notion", "brex", "affirm", "instacart",
        "doordash", "reddit", "pinterest", "coinbase", "robinhood",
        "figma", "vercel", "netlify", "linear", "supabase",
        "snowflake", "databricks", "dropbox", "sentry",
    ],
    "ai-tooling": [
        "huggingface", "weaviate", "pinecone", "modal", "replicate",
        "together", "fireworksai", "openpipe", "arizeai",
        "labelbox", "scaleai", "gretelai", "weights-and-biases",
        "cleanlab", "unstructured",
    ],
    "healthcare-ai": [
        "verilyhealthworks", "flatironhealth", "tempus", "insitro",
        "recursion", "abridge", "hingehealth", "commure",
        "colormedicine", "hearthealth", "curai",
    ],
    "robotics": [
        "figure", "1x", "skydio", "coco", "nurorobotics", "farm-ng",
        "bearrobotics", "verilyroboticssurgical",
    ],
    "data-infra": [
        "snowflake", "confluent", "elastic", "mongodb", "cockroachlabs",
        "airbyte", "dbt-labs", "prefect", "hex-technologies",
    ],
}

# ---------- Lever ----------------------------------------------------------

LEVER_PACKS: dict[str, list[str]] = {
    "ai-labs": [
        "mistral", "eleuther-ai", "sakana", "adept",
    ],
    "big-tech-ai": [
        "netflix", "palantir", "spotify", "shopify", "cloudflare",
        "roblox", "twitch", "flexport", "carta", "gusto",
    ],
    "ai-tooling": [
        "clari", "arcee-ai", "arize", "predibase", "voxel",
    ],
    "healthcare-ai": [
        "collectivehealth", "veevasystems", "cleerly", "atrophic",
    ],
    "robotics": [
        "cruise", "nuro", "zoox", "aurora",
    ],
    "data-infra": [
        "starburst", "materialize", "monteCarloData",
    ],
}

# ---------- Ashby ----------------------------------------------------------

ASHBY_PACKS: dict[str, list[str]] = {
    "ai-labs": [
        "anthropic",  # Anthropic runs Ashby for some public postings.
        "harveyai", "openevidence", "clay",
    ],
    "ai-tooling": [
        "browsercompany", "cursor", "warp", "granola", "supermaven",
        "vercel",  # dual-listed
    ],
    "healthcare-ai": [
        "openevidence", "abridge", "commure",
    ],
    "robotics": [
        "physical-intelligence", "skild-ai",
    ],
}

# ---------- Workable -------------------------------------------------------

WORKABLE_PACKS: dict[str, list[str]] = {
    "ai-labs": [
        # Workable is more common with EU-heavy startups; kept small.
        "cohere-labs",
    ],
    "healthcare-ai": [
        "medable", "biofourmis",
    ],
}


# --------------------------------------------------------------------------
# Resolution helpers used by settings + registry.

_PACK_INDEX: dict[str, dict[str, list[str]]] = {
    "greenhouse": GREENHOUSE_PACKS,
    "lever": LEVER_PACKS,
    "ashby": ASHBY_PACKS,
    "workable": WORKABLE_PACKS,
}


def resolve_companies(provider: str, pack_names: list[str]) -> list[str]:
    """Expand pack names into a de-duplicated slug list for one provider.

    Unknown pack names are silently skipped (typo-tolerant); callers get
    the union of everything that resolves.
    """

    packs = _PACK_INDEX.get(provider, {})
    seen: set[str] = set()
    out: list[str] = []
    for name in pack_names:
        for slug in packs.get(name.strip().lower(), []):
            key = slug.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(slug.strip())
    return out


def available_packs(provider: str) -> list[str]:
    """Return the pack names available for ``provider``."""

    return sorted(_PACK_INDEX.get(provider, {}).keys())
