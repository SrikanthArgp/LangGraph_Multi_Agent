from auth.password import hash_password, verify_password


def test_hash_and_verify_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_wrong_password_fails_verification():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_same_password_hashes_differently_each_time():
    first = hash_password("same password")
    second = hash_password("same password")
    assert first != second
    assert verify_password("same password", first)
    assert verify_password("same password", second)


def test_passwords_longer_than_72_bytes_still_hash_and_verify():
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)
    assert verify_password("x" * 72, hashed)
