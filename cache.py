import time
from functools import wraps

# Simple in-memory cache with a TTL
_cache = {}
_TTL = 300  # 5 minutes

def timed_cache(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Create a cache key from the function name and arguments
        key = f"{func.__name__}:{args}:{kwargs}"

        current_time = time.time()

        if key in _cache:
            data, timestamp = _cache[key]
            if current_time - timestamp < _TTL:
                return data

        # If not in cache or expired, call the function and store the result
        result = func(*args, **kwargs)
        _cache[key] = (result, current_time)
        return result

    return wrapper

def yf_download_cached(*args, **kwargs):
    """
    A cached wrapper for yf.download to avoid hitting the API too frequently.
    """
    import yfinance as yf

    @timed_cache
    def _download(*args, **kwargs):
        return yf.download(*args, **kwargs)

    return _download(*args, **kwargs)