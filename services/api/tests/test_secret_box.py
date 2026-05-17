import base64
import os

import pytest

from app.security.secret_box import (
    SecretBox,
    SecretBoxConfigError,
    _derive_fernet_key,
    reset_secret_box_for_tests,
)


def setup_function() -> None:
    reset_secret_box_for_tests()


def test_round_trip_encrypts_and_decrypts_value() -> None:
    key = base64.urlsafe_b64encode(os.urandom(32))
    box = SecretBox(key)

    ciphertext = box.encrypt("sk-test-value")
    assert ciphertext != "sk-test-value"
    assert box.decrypt(ciphertext) == "sk-test-value"


def test_decrypt_with_wrong_key_raises_config_error() -> None:
    primary = SecretBox(base64.urlsafe_b64encode(os.urandom(32)))
    other = SecretBox(base64.urlsafe_b64encode(os.urandom(32)))

    ciphertext = primary.encrypt("secret")
    with pytest.raises(SecretBoxConfigError):
        other.decrypt(ciphertext)


def test_derive_key_accepts_valid_fernet_key() -> None:
    valid = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    derived = _derive_fernet_key(valid, "production")
    assert derived == valid.encode("ascii")


def test_derive_key_hashes_arbitrary_secret() -> None:
    derived = _derive_fernet_key("not-a-fernet-key", "production")
    assert len(base64.urlsafe_b64decode(derived)) == 32


def test_derive_key_requires_secret_in_production() -> None:
    with pytest.raises(SecretBoxConfigError):
        _derive_fernet_key("", "production")


def test_derive_key_falls_back_in_development() -> None:
    derived = _derive_fernet_key("", "development")
    assert len(base64.urlsafe_b64decode(derived)) == 32
