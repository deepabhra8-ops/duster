from __future__ import annotations

import hashlib

import pytest

from common.security import password_hash
from common.security.password_hash import (
    classify,
    hash_password,
    retag_bare_sha256,
    verify_password,
)


def _bare(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class TestHashPassword:
    def test_produces_tagged_format(self):
        assert hash_password("hunter2") == f"sha256${_bare('hunter2')}"

    def test_is_deterministic(self):
        assert hash_password("hunter2") == hash_password("hunter2")

    def test_differs_by_password(self):
        assert hash_password("a") != hash_password("b")

    def test_handles_unicode(self):
        assert hash_password("pässwörd") == f"sha256${_bare('pässwörd')}"


class TestVerifyTagged:
    def test_accepts_correct_password(self):
        assert verify_password("hunter2", hash_password("hunter2")) == (True, False)

    def test_rejects_wrong_password(self):
        assert verify_password("wrong", hash_password("hunter2")) == (False, False)

    def test_rejects_unknown_algorithm(self):
        ok, needs_rehash = verify_password("hunter2", "md5$abc123")
        assert (ok, needs_rehash) == (False, False)


class TestVerifyLegacyBareDigest:
    def test_accepts_and_flags_for_rehash(self):
        assert verify_password("hunter2", _bare("hunter2")) == (True, True)

    def test_rejects_wrong_password_without_rehash(self):
        assert verify_password("wrong", _bare("hunter2")) == (False, True)


class TestVerifyLegacyPlaintext:
    def test_accepts_and_flags_for_rehash_when_allowed(self, monkeypatch):
        monkeypatch.setattr(password_hash, "AUTH_ALLOW_LEGACY_PLAINTEXT", True)
        assert verify_password("hunter2", "hunter2") == (True, True)

    def test_rejects_wrong_password_when_allowed(self, monkeypatch):
        monkeypatch.setattr(password_hash, "AUTH_ALLOW_LEGACY_PLAINTEXT", True)
        assert verify_password("wrong", "hunter2") == (False, True)

    def test_rejects_entirely_when_disallowed(self, monkeypatch):
        monkeypatch.setattr(password_hash, "AUTH_ALLOW_LEGACY_PLAINTEXT", False)
        assert verify_password("hunter2", "hunter2") == (False, False)


class TestEmptyValues:
    @pytest.mark.parametrize(
        "submitted,stored",
        [("", hash_password("x")), ("x", ""), ("x", None), ("", "")],
    )
    def test_empty_never_verifies(self, submitted, stored):
        assert verify_password(submitted, stored) == (False, False)


class TestClassify:
    @pytest.mark.parametrize(
        "stored,expected",
        [
            (hash_password("x"), "tagged"),
            (_bare("x"), "bare_sha256"),
            ("plaintextpw", "plaintext"),
            ("md5$abc", "plaintext"),
            (_bare("x").upper(), "plaintext"),
            ("", "plaintext"),
            (None, "plaintext"),
        ],
    )
    def test_classify(self, stored, expected):
        assert classify(stored) == expected


class TestRetag:
    def test_wraps_a_bare_digest(self):
        assert retag_bare_sha256(_bare("x")) == f"sha256${_bare('x')}"

    def test_retagged_value_still_verifies(self):
        assert verify_password("x", retag_bare_sha256(_bare("x"))) == (True, False)

    def test_refuses_a_non_digest(self):
        with pytest.raises(ValueError):
            retag_bare_sha256("not-a-digest")


class TestKnownLimitation:
    def test_a_64_hex_char_plaintext_password_is_unusable(self, monkeypatch):
        monkeypatch.setattr(password_hash, "AUTH_ALLOW_LEGACY_PLAINTEXT", True)
        stored = "a" * 64

        ok, _ = verify_password(stored, stored)

        assert ok is False
