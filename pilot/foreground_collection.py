"""Explicit deployment support, not evidence of a successful platform login/run."""
from pydantic import ValidationError

from pilot.research_strategy_contract import ResearchStrategyConfiguration


def foreground_collection_policy(platform, access_mode, configuration):
    return platform == 'XIAOHONGSHU' and three_platform_collection_policy(platform, access_mode, configuration)


def three_platform_collection_policy(platform, access_mode, configuration):
    if platform not in ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI') or access_mode != 'PLATFORM_ACCOUNT':
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
    if mode == 'three-platform-foreground-v1':
        return three_platform_collection_policy
    if mode == 'three-platform-monitor-v1':
        return three_platform_monitor_policy
    raise RuntimeError('invalid_collection_configuration')


def three_platform_monitor_policy(platform, access_mode, configuration):
    """Backend support only; monitor START separately requires a reserved slot."""
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return False
    if parsed.mode == 'once':
        return three_platform_collection_policy(platform, access_mode, configuration)
    if getattr(parsed.schedule, 'policyVersion', None) != 1:
        return False
    # Validate the same search surface without modifying the stored strategy
    # snapshot, its digest, or the execution request's monitor intent.
    search = parsed.model_dump(mode='json') | {'mode': 'once', 'schedule': None}
    return three_platform_collection_policy(platform, access_mode, search)


def foreground_collection_support(runtime, claims):
    with runtime.database.connect() as connection, connection.cursor() as cursor:
        runtime._active(cursor, claims)
        mode = 'xhs-foreground-v1' if runtime.capability_check is foreground_collection_policy else None
        if runtime.capability_check in (three_platform_collection_policy, three_platform_monitor_policy):
            mode = 'three-platform-foreground-v1'
        runtime._active(cursor, claims)
        return {'schema_version':'foreground-collection-support-v1', 'mode':mode}
