"""Explicit deployment support, not evidence of a successful platform login/run."""
from pydantic import ValidationError

from pilot.research_strategy_contract import ResearchStrategyConfiguration


def foreground_collection_policy(platform, access_mode, configuration):
    return platform == 'XIAOHONGSHU' and three_platform_collection_policy(platform, access_mode, configuration)


def three_platform_collection_policy(platform, access_mode, configuration):
    return _collection_policy(platform, access_mode, configuration, ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI'))


def four_platform_collection_policy(platform, access_mode, configuration):
    return _collection_policy(platform, access_mode, configuration, ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU'))


def _collection_policy(platform, access_mode, configuration, platforms):
    if platform not in platforms or access_mode != 'PLATFORM_ACCOUNT':
        return False
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return False
    return (parsed.source == 'search' and parsed.mode == 'once'
            and parsed.schedule is None and parsed.research is None
            # Confirmed exclusions are applied to validated source records by
            # the native driver, not sent as platform search operators.
            and not parsed.links
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
    if mode == 'four-platform-foreground-v1':
        return four_platform_collection_policy
    if mode == 'four-platform-monitor-v1':
        return four_platform_monitor_policy
    if mode == 'four-platform-public-monitor-v1':
        return four_platform_public_monitor_policy
    if mode == 'four-platform-public-sampling-monitor-v1':
        return four_platform_public_sampling_monitor_policy
    raise RuntimeError('invalid_collection_configuration')


def three_platform_monitor_policy(platform, access_mode, configuration):
    """Backend support only; monitor START separately requires a reserved slot."""
    return _monitor_policy(platform, access_mode, configuration, three_platform_collection_policy)


def four_platform_monitor_policy(platform, access_mode, configuration):
    return _monitor_policy(platform, access_mode, configuration, four_platform_collection_policy)


def four_platform_public_monitor_policy(platform, access_mode, configuration):
    """Explicit V2EX recent-topic sampling, not anonymous full-site search/monitor."""
    if platform != 'PUBLIC_WEB':
        return four_platform_monitor_policy(platform, access_mode, configuration)
    if access_mode != 'PUBLIC_ANONYMOUS':
        return False
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return False
    return (parsed.publicSource == 'v2ex-latest-v1'
            and parsed.source == 'search' and parsed.mode == 'once'
            and parsed.schedule is None and parsed.research is None
            and not parsed.links and bool(parsed.keywords)
            and all(term == term.strip() and ',' not in term for term in parsed.keywords))


def four_platform_public_sampling_monitor_policy(platform, access_mode, configuration):
    """Periodic latest-topic samples; never promises historical/full-site coverage."""
    if platform != 'PUBLIC_WEB':
        return four_platform_monitor_policy(platform, access_mode, configuration)
    return _monitor_policy(platform, access_mode, configuration, four_platform_public_monitor_policy)


def _monitor_policy(platform, access_mode, configuration, collection_policy):
    try:
        parsed = ResearchStrategyConfiguration.model_validate(configuration)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return False
    if parsed.mode == 'once':
        return collection_policy(platform, access_mode, configuration)
    if getattr(parsed.schedule, 'policyVersion', None) != 1:
        return False
    # Validate the same search surface without modifying the stored strategy
    # snapshot, its digest, or the execution request's monitor intent.
    search = parsed.model_dump(mode='json') | {'mode': 'once', 'schedule': None}
    return collection_policy(platform, access_mode, search)


def foreground_collection_support(runtime, claims):
    with runtime.database.connect() as connection, connection.cursor() as cursor:
        runtime._active(cursor, claims)
        mode = 'xhs-foreground-v1' if runtime.capability_check is foreground_collection_policy else None
        if runtime.capability_check in (three_platform_collection_policy, three_platform_monitor_policy):
            mode = 'three-platform-foreground-v1'
        if runtime.capability_check in (four_platform_collection_policy, four_platform_monitor_policy,
                                       four_platform_public_monitor_policy, four_platform_public_sampling_monitor_policy):
            mode = 'four-platform-foreground-v1'
        runtime._active(cursor, claims)
        result = {'schema_version':'foreground-collection-support-v1', 'mode':mode}
        if runtime.capability_check in (four_platform_public_monitor_policy, four_platform_public_sampling_monitor_policy):
            result['public_source'] = 'v2ex-latest-v1'
        if runtime.capability_check is four_platform_public_sampling_monitor_policy:
            result['public_monitor'] = True
        return result
