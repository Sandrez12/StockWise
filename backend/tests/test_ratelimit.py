from app.ratelimit import LoginRateLimiter


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(**kw):
    clock = Clock()
    return LoginRateLimiter(clock=clock, **kw), clock


def test_not_blocked_until_five_failures():
    limiter, _ = make()
    for _ in range(4):
        limiter.register_failure("1.1.1.1", "a@x.com")
        assert limiter.retry_after("1.1.1.1", "a@x.com") == 0
    limiter.register_failure("1.1.1.1", "a@x.com")
    assert limiter.retry_after("1.1.1.1", "a@x.com") > 0


def test_retry_after_is_bounded_by_window():
    limiter, clock = make()
    for _ in range(5):
        limiter.register_failure("1.1.1.1", "a@x.com")
    assert 1 <= limiter.retry_after("1.1.1.1", "a@x.com") <= 15 * 60 + 1
    clock.now += 600
    assert 1 <= limiter.retry_after("1.1.1.1", "a@x.com") <= 300 + 1


def test_block_expires_after_window():
    limiter, clock = make()
    for _ in range(5):
        limiter.register_failure("1.1.1.1", "a@x.com")
    clock.now += 15 * 60
    assert limiter.retry_after("1.1.1.1", "a@x.com") == 0


def test_old_failures_do_not_count():
    limiter, clock = make()
    for _ in range(4):
        limiter.register_failure("1.1.1.1", "a@x.com")
    clock.now += 15 * 60 + 1
    limiter.register_failure("1.1.1.1", "a@x.com")
    assert limiter.retry_after("1.1.1.1", "a@x.com") == 0


def test_keys_are_independent_by_ip_and_email():
    limiter, _ = make()
    for _ in range(5):
        limiter.register_failure("1.1.1.1", "a@x.com")
    assert limiter.retry_after("2.2.2.2", "a@x.com") == 0
    assert limiter.retry_after("1.1.1.1", "b@x.com") == 0


def test_email_is_case_and_space_insensitive():
    limiter, _ = make()
    for _ in range(5):
        limiter.register_failure("1.1.1.1", "A@X.com ")
    assert limiter.retry_after("1.1.1.1", "a@x.com") > 0


def test_reset_clears_failures():
    limiter, _ = make()
    for _ in range(5):
        limiter.register_failure("1.1.1.1", "a@x.com")
    limiter.reset("1.1.1.1", "a@x.com")
    assert limiter.retry_after("1.1.1.1", "a@x.com") == 0


def test_memory_is_bounded():
    limiter, _ = make(max_keys=50)
    for i in range(500):
        limiter.register_failure("1.1.1.1", f"u{i}@x.com")
    assert len(limiter._failures) <= 50


def test_expired_keys_are_dropped():
    limiter, clock = make()
    limiter.register_failure("1.1.1.1", "a@x.com")
    clock.now += 15 * 60 + 1
    assert limiter.retry_after("1.1.1.1", "a@x.com") == 0
    assert len(limiter._failures) == 0
