"""Explicit deployment support, not evidence of a successful platform login/run."""
from pydantic import ValidationError

from pilot.research_strategy_contract import ResearchStrategyConfiguration


def foreground_collection_policy(platform, access_mode, configuration):
    if platform != 'XIAOHONGSHU' or access_mode != 'PLATFORM_ACCOUNT':
        return False
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return False
    return (parsed.source == 'search' and parsed.mode == 'once'
            and parsed.schedule is None and parsed.research is None
            and not parsed.exclusions and not parsed.links
            and bool(parsed.keywords)
            and all(term == term.strip() and ',' not in term for term in parsed.keywords))


def configured_collection_policy(environment):
    mode = environment.get('YIKE_PILOT_COLLECTION_MODE', '')
    if mode == '':
        return None
    if mode == 'xhs-foreground-v1':
        return foreground_collection_policy
    raise RuntimeError('invalid_collection_configuration')


def foreground_collection_support(runtime, claims):
    with runtime.database.connect() as connection, connection.cursor() as cursor:
        runtime._active(cursor, claims)
        mode = 'xhs-foreground-v1' if runtime.capability_check is foreground_collection_policy else None
        runtime._active(cursor, claims)
        return {'schema_version':'foreground-collection-support-v1', 'mode':mode}
