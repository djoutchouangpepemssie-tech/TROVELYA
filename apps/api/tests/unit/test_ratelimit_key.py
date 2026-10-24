from trovelya.core.ratelimit import client_fingerprint


def test_fingerprint_hides_the_ip_and_is_stable() -> None:
    first = client_fingerprint("92.170.253.181", secret="s" * 64)
    assert "92.170.253.181" not in first
    assert first == client_fingerprint("92.170.253.181", secret="s" * 64)
    assert first != client_fingerprint("92.170.253.182", secret="s" * 64)


def test_fingerprint_depends_on_the_secret() -> None:
    # Keyed: an attacker cannot rebuild it by hashing the 2^32 IPv4 addresses.
    assert client_fingerprint("1.2.3.4", secret="a" * 64) != client_fingerprint(
        "1.2.3.4", secret="b" * 64
    )
