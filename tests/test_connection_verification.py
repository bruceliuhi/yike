"""VERIFY is a bound owner-client observation, never server platform proof."""
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.connection_versions import ConnectionOperation, ConnectionOperationError


def verification(**changes):
    return dict(request_id=str(uuid4()), action='VERIFY', device_id=str(uuid4()),
        connection_id=str(uuid4()), expected_connection_version=1,
        platform='XIAOHONGSHU', account_public_id='original-public-id',
        session_ref='vault://device/xhs/opaque-profile') | changes


def test_verify_accepts_exact_bound_observation_and_hides_profile():
    payload=verification()
    request=ConnectionOperation(**payload)
    assert request.model_dump()==payload and len(payload)==8
    assert payload['session_ref'] not in repr(request)


@pytest.mark.parametrize('changes', [
    {'connection_id':None}, {'connection_id':str(uuid4()).upper()},
    {'connection_id':'not-uuid'}, {'expected_connection_version':0},
    {'expected_connection_version':True}, {'expected_connection_version':'1'},
    {'expected_connection_version':2147483648}, {'platform':None}, {'platform':'xiaohongshu'},
    {'account_public_id':None}, {'account_public_id':' original-public-id'},
    {'account_public_id':'token=private-marker'}, {'account_public_id':'public\nprivate-marker'},
    {'session_ref':None}, {'session_ref':' vault://private-marker'},
    {'session_ref':'vault://token=private-marker'}, {'unexpected':'private-marker'},
])
def test_verify_rejects_noncanonical_or_incomplete_binding(changes):
    with pytest.raises((ValidationError,ConnectionOperationError)) as error:
        ConnectionOperation(**verification(**changes))
    assert 'private-marker' not in str(error.value)


@pytest.mark.parametrize('field', list(verification()))
def test_verify_requires_every_field(field):
    payload=verification(); del payload[field]
    with pytest.raises((ValidationError,ConnectionOperationError)):
        ConnectionOperation(**payload)


def test_verification_migration_registered_and_does_not_rewrite_old_migration():
    from pilot.db import PilotDatabase
    assert ('v02-connection-verification',Path(__file__).resolve().parents[1]/
        'migrations/119_v02_connection_verification.sql') in PilotDatabase.migration_paths
