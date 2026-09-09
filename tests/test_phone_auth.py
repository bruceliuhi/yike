import importlib

import pytest


def test_phone_auth_core_exists():
    assert importlib.util.find_spec('pilot.phone_auth') is not None


@pytest.mark.parametrize('secret', [b'', b'x' * 31, 'x' * 32, None])
def test_secret_validation(secret):
    from pilot.phone_auth import PhoneAuthStore, PhoneAuthError
    with pytest.raises(PhoneAuthError):
        PhoneAuthStore(None, secret)


@pytest.mark.parametrize('phone', ['', '13800000000 ', '+8613800000000', '１3800000000', None, 13800000000, '1' * 10000])
def test_phone_validation_before_database(phone):
    from pilot.phone_auth import PhoneAuthStore, PhoneAuthError
    with pytest.raises(PhoneAuthError, match='invalid_phone'):
        PhoneAuthStore(None, b'x' * 32).reserve(phone, '127.0.0.1')


@pytest.mark.parametrize('peer', ['', 'x' * 257, None, 'bad\npeer'])
def test_peer_validation_before_database(peer):
    from pilot.phone_auth import PhoneAuthStore, PhoneAuthError
    with pytest.raises(PhoneAuthError):
        PhoneAuthStore(None, b'x' * 32).reserve('13800000000', peer)


def test_repr_and_domain_separation():
    from pilot.phone_auth import PhoneAuthStore
    store = PhoneAuthStore(None, b'sensitive-secret-material-123456789')
    assert 'sensitive' not in repr(store)
    assert store._digest('phone', '13800000000') != store._digest('peer', '13800000000')


@pytest.mark.parametrize('code', ['１２３４５６', '12345', '1234567', None, 123456])
def test_code_validation(code):
    from pilot.phone_auth import PhoneAuthStore, PhoneAuthError
    with pytest.raises(PhoneAuthError, match='invalid_code'):
        PhoneAuthStore(None, b'x' * 32).consume('13800000000', code)
