from app.auth.passwords import hash_password, needs_rehash, verify_password


def test_hash_is_argon2id_and_not_the_password() -> None:
    hashed = hash_password("a-long-password")

    assert hashed.startswith("$argon2id$")
    assert "a-long-password" not in hashed


def test_verify_accepts_correct_and_rejects_wrong_password() -> None:
    hashed = hash_password("a-long-password")

    assert verify_password(hashed, "a-long-password")
    assert not verify_password(hashed, "A-long-password")


def test_same_password_hashes_differently() -> None:
    assert hash_password("a-long-password") != hash_password("a-long-password")


def test_invalid_hash_is_a_failed_verification_not_a_crash() -> None:
    assert not verify_password("not-a-hash", "anything")


def test_fresh_hash_does_not_need_rehash() -> None:
    assert not needs_rehash(hash_password("a-long-password"))
