"""Policy v1 calendar math only; a future date is not an execution receipt."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from pilot.research_strategy_contract import _VersionedSchedule


def _first_instant(day, hhmm, zone):
    local = datetime.combine(day, time.fromisoformat(hhmm))
    valid = []
    for fold in (0, 1):
        instant = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            valid.append(instant)
    return min(valid) if valid else None


def next_occurrence(schedule, *, after: datetime) -> datetime:
    """Strictly future UTC slot; no replay of missed slots or timezone fallback.

    DST gaps skip daily slots / whole interval windows. Repeated wall-clock
    boundaries resolve to the first instant. Intervals count elapsed hours.
    """
    value = _VersionedSchedule.model_validate(schedule)
    if not isinstance(after, datetime) or after.tzinfo is None or after.utcoffset() is None:
        raise ValueError('aware server time required')
    after = after.astimezone(timezone.utc)
    zone = ZoneInfo(value.timezone)
    today = after.astimezone(zone).date()
    candidates = []
    try:
        # Yesterday covers a still-open overnight window. Eight future days
        # cover a skipped calendar date without an unbounded schedule loop.
        for offset in range(-1, 9):
            day = today + timedelta(days=offset)
            if value.kind == 'daily':
                for hhmm in value.times:
                    instant = _first_instant(day, hhmm, zone)
                    if instant is not None and instant > after:
                        candidates.append(instant)
                continue
            end_day = day + timedelta(days=value.end < value.start)
            start = _first_instant(day, value.start, zone)
            end = _first_instant(end_day, value.end, zone)
            if start is None or end is None:
                continue
            step = timedelta(hours=value.interval)
            instant = start
            if instant <= after:
                instant += ((after - instant) // step + 1) * step
            if instant < end:
                candidates.append(instant)
    except (OverflowError, OSError):
        raise ValueError('unsupported calendar range') from None
    if not candidates:
        raise ValueError('no future schedule slot')
    return min(candidates)
