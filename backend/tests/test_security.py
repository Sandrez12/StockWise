import time
from datetime import timedelta

import jwt
import pytest

from app.config import get_settings
from app.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_argon2_and_not_plaintext():
    hashed = hash_password("una-contraseña-larga")
    assert hashed.startswith("$argon2")
    assert "una-contraseña-larga" not in hashed


def test_hash_is_salted():
    assert hash_password("misma-contraseña-1") != hash_password("misma-contraseña-1")


def test_verify_password():
    hashed = hash_password("correcta-correcta")
    assert verify_password("correcta-correcta", hashed)
    assert not verify_password("incorrecta-incorrecta", hashed)


def test_verify_password_with_unknown_hash_format_is_false():
    assert not verify_password("x", "esto-no-es-un-hash")


def test_token_roundtrip():
    claims = decode_access_token(create_access_token("42"))
    assert claims["sub"] == "42"
    assert claims["exp"] - claims["iat"] == 30 * 60


def test_expired_token_is_rejected():
    token = create_access_token("1", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_key_is_rejected():
    forged = jwt.encode({"sub": "1", "exp": time.time() + 600}, "o" * 40, algorithm=ALGORITHM)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_tampered_payload_is_rejected():
    header, _payload, signature = create_access_token("1").split(".")
    other = create_access_token("2").split(".")[1]
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{other}.{signature}")


def test_unsigned_token_is_rejected():
    token = jwt.encode({"sub": "1", "exp": time.time() + 600}, key=None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_token_without_subject_is_rejected():
    token = jwt.encode(
        {"exp": time.time() + 600}, get_settings().secret_key, algorithm=ALGORITHM
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)
