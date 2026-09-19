import time
from collections import defaultdict

_bucket = defaultdict(list)


def allow(user_id: int, key: str = "default", limit_sec: int = 1) -> bool:
    """True — можно, False — слишком часто."""
    now = time.time()
    bucket = _bucket[(user_id, key)]
    bucket[:] = [t for t in bucket if now - t < limit_sec]
    if bucket:
        return False
    bucket.append(now)
    return True
