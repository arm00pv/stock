import time

# --- Simple In-Memory Cache with TTL ---

CACHE_TTL_SECONDS = 300  # 5 minutes
_cache = {}

def set(key, value):
    """
    Stores a value in the cache with the current timestamp.
    """
    _cache[key] = {
        'value': value,
        'timestamp': time.time()
    }

def get(key):
    """
    Retrieves a value from the cache if it exists and has not expired.
    Returns None if the key is not found or the item has expired.
    """
    item = _cache.get(key)
    if item is None:
        return None

    # Check if the item has expired
    if time.time() - item['timestamp'] > CACHE_TTL_SECONDS:
        # Item has expired, remove it from the cache
        del _cache[key]
        return None

    return item['value']

def flush():
    """
    Clears the entire cache.
    """
    _cache.clear()
