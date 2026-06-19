from backend.shared import auth


def test_hash_password_returns_bytes_or_str_hash():
    h = auth.hash_password("hunter2")
    assert isinstance(h, str)
    assert h != "hunter2"
    assert h.startswith("$2b$")


def test_hash_password_unique_per_call():
    """bcrypt salts each hash."""
    h1 = auth.hash_password("hunter2")
    h2 = auth.hash_password("hunter2")
    assert h1 != h2


def test_verify_password_correct():
    h = auth.hash_password("hunter2")
    assert auth.verify_password("hunter2", h) is True


def test_verify_password_wrong():
    h = auth.hash_password("hunter2")
    assert auth.verify_password("WRONG", h) is False


def test_verify_password_handles_invalid_hash():
    """Garbage hash should return False, not crash."""
    assert auth.verify_password("any", "not-a-valid-hash") is False


def test_generate_session_token_length():
    t = auth.generate_session_token()
    assert isinstance(t, str)
    assert len(t) >= 32


def test_generate_session_token_unique():
    tokens = {auth.generate_session_token() for _ in range(100)}
    assert len(tokens) == 100


def test_hash_session_token_is_deterministic_and_one_way():
    token = "raw-bearer-token"
    hashed = auth.hash_session_token(token)
    assert hashed.startswith("sha256:")
    assert len(hashed) == len("sha256:") + 64
    assert token not in hashed
    assert auth.hash_session_token(token) == hashed
    assert auth.hash_session_token("different") != hashed


def test_hash_ip_returns_64_char_hex():
    h = auth.hash_ip("203.0.113.7")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_ip_deterministic():
    assert auth.hash_ip("1.2.3.4") == auth.hash_ip("1.2.3.4")


def test_hash_ip_different_inputs():
    assert auth.hash_ip("1.2.3.4") != auth.hash_ip("1.2.3.5")
