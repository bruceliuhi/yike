"""Same-transaction eligibility check for an optional research provenance."""
from __future__ import annotations

import psycopg

from pilot.opportunity_research import OpportunityResearchError, OpportunityResearchService
from pilot.research_strategy_contract import StrategyStoreError


def validate_research_origin(cursor, database, claims, tenant, profile_version_id, configuration):
    """Validate current recognized-source eligibility without opening a connection."""
    research = configuration.get("research") if type(configuration) is dict else None
    provenance = research.get("provenance") if type(research) is dict else None
    if provenance is None:
        return
    try:
        if provenance["profileVersionId"] != profile_version_id:
            raise OpportunityResearchError("binding_conflict", 409)
        binding = {key: provenance[key] for key in (
            "userId", "opportunityId", "profileVersionId", "sourceUrl", "evidenceVersion", "accountScope")}
        # The strict strategy contract already validated this persisted shape.
        # Do not reuse _binding here: its generic 512-character identity loop
        # predates the provenance contract's explicit 2048-character URL bound.
        service = OpportunityResearchService(database, supported_platforms=())
        evidence = service._recognized(cursor, tenant, claims, binding)
        cursor.execute("SELECT clock_timestamp()")
        service._current_recognition(cursor, tenant, claims, binding, evidence, cursor.fetchone()[0])
    except OpportunityResearchError as error:
        if error.code == "research_store_unavailable":
            raise StrategyStoreError("strategy_store_unavailable", 503) from None
        raise StrategyStoreError("research_origin_unavailable", 409) from None
    except (KeyError, TypeError, ValueError):
        raise StrategyStoreError("research_origin_unavailable", 409) from None
    except psycopg.Error:
        raise
