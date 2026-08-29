from app.core.security import (
    api_key_prefix,
    generate_api_key,
    has_valid_api_key_shape,
    hash_api_key,
)


def test_api_keys_are_high_entropy_and_hash_deterministically() -> None:
    raw_key = generate_api_key()

    first_hash = hash_api_key(raw_key, "test-pepper")
    second_hash = hash_api_key(raw_key, "test-pepper")

    assert has_valid_api_key_shape(raw_key)
    assert len(first_hash) == 64
    assert first_hash == second_hash
    assert raw_key not in first_hash
    assert api_key_prefix(raw_key) == raw_key[:12]


def test_api_key_hash_changes_with_the_server_pepper() -> None:
    raw_key = generate_api_key()

    assert hash_api_key(raw_key, "pepper-a") != hash_api_key(raw_key, "pepper-b")
