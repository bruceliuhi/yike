from datetime import datetime, timezone

import pytest

from pilot.monitor_calendar import next_occurrence


def at(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def schedule(**changes):
    return dict(kind='daily', times=['09:30'], interval=2, start='09:00', end='18:00',
                timezone='Asia/Shanghai', policyVersion=1) | changes


@pytest.mark.parametrize('after, expected', [
    ('2026-09-11T01:29:59Z', '2026-09-11T01:30:00Z'),
    ('2026-09-11T01:30:00Z', '2026-09-12T01:30:00Z'),
    ('2026-09-20T02:00:00Z', '2026-09-21T01:30:00Z'),
])
def test_daily_is_strictly_future_without_catchup(after, expected):
    assert next_occurrence(schedule(), after=at(after)) == at(expected)


def test_daily_times_are_order_independent():
    result = next_occurrence(schedule(times=['18:00', '09:30', '13:00']),
                             after=at('2026-09-11T02:00:00Z'))
    assert result == at('2026-09-11T05:00:00Z')
    assert result.tzinfo is timezone.utc


def test_daily_skips_nonexistent_dst_and_uses_only_first_repeated_time():
    spring = schedule(timezone='America/New_York', times=['02:30'])
    assert next_occurrence(spring, after=at('2026-03-08T06:00:00Z')) == at('2026-03-09T06:30:00Z')
    fall = schedule(timezone='America/New_York', times=['01:30'])
    assert next_occurrence(fall, after=at('2026-11-01T04:00:00Z')) == at('2026-11-01T05:30:00Z')
    assert next_occurrence(fall, after=at('2026-11-01T05:30:00Z')) == at('2026-11-02T06:30:00Z')


def test_interval_crosses_midnight_anchored_not_poll_time():
    value = schedule(kind='interval', start='22:00', end='04:00', interval=2)
    assert next_occurrence(value, after=at('2026-09-11T16:01:00Z')) == at('2026-09-11T18:00:00Z')
    assert next_occurrence(value, after=at('2026-09-11T18:00:00Z')) == at('2026-09-12T14:00:00Z')


def test_interval_uses_elapsed_hours_across_fall_dst():
    value = schedule(kind='interval', timezone='America/New_York', start='00:00', end='04:00', interval=2)
    assert next_occurrence(value, after=at('2026-11-01T04:00:00Z')) == at('2026-11-01T06:00:00Z')
    assert next_occurrence(value, after=at('2026-11-01T06:00:00Z')) == at('2026-11-01T08:00:00Z')


def test_interval_skips_entire_window_if_either_boundary_missing():
    value = schedule(kind='interval', timezone='America/New_York', start='01:00', end='02:30', interval=1)
    assert next_occurrence(value, after=at('2026-03-08T05:00:00Z')) == at('2026-03-09T05:00:00Z')


def test_interval_fraction_and_end_exclusion():
    value = schedule(kind='interval', start='09:00', end='12:00', interval=1.5)
    assert next_occurrence(value, after=at('2026-09-11T01:00:00Z')) == at('2026-09-11T02:30:00Z')
    assert next_occurrence(value, after=at('2026-09-11T02:30:00Z')) == at('2026-09-12T01:00:00Z')


@pytest.mark.parametrize('change', [dict(policyVersion=None), dict(policyVersion=True),
    dict(timezone='not/a/timezone'), dict(kind='interval', start='09:00', end='09:00')])
def test_rejects_unsupported_schedule(change):
    with pytest.raises(ValueError):
        next_occurrence(schedule(**change), after=at('2026-09-11T00:00:00Z'))


def test_rejects_naive_clock_and_unversioned_intent():
    with pytest.raises(ValueError):
        next_occurrence(schedule(), after=datetime(2026, 9, 11))
    value = schedule()
    del value['policyVersion']
    with pytest.raises(ValueError):
        next_occurrence(value, after=at('2026-09-11T00:00:00Z'))
