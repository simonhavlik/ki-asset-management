"""Cache invalidation via namespace generations.

Flask-Caching can only delete exact keys, but our cached keys carry arguments
(page, limit, ...). Deleting a bare prefix silently missed them, so the ideas
wall kept serving a stale page after a comment was added. These tests pin the
generation mechanism that replaced the prefix delete.
"""

from app.utils import neon_cache


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _with_fake_cache(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(neon_cache, "_cache_instance", fake)
    monkeypatch.setattr(neon_cache, "NEON_OPTIMIZE", True)
    return fake


def test_bump_changes_the_generation(monkeypatch):
    _with_fake_cache(monkeypatch)

    before = neon_cache._cache_generation("wall")
    neon_cache._bump_cache_generation("wall")
    after = neon_cache._cache_generation("wall")

    assert before != after


def test_page_cache_key_carries_the_generation(monkeypatch):
    _with_fake_cache(monkeypatch)

    def wall_key():
        return neon_cache.get_cache_key(
            neon_cache.KEY_PREFIX["wall_page"],
            neon_cache._cache_generation("wall"),
            1,
            12,
        )

    key_before = wall_key()
    neon_cache.invalidate_wall_cache()
    key_after = wall_key()

    assert key_before != key_after, "wall invalidation must change the page key"


def test_blog_invalidation_bumps_research_generation(monkeypatch):
    """The featured-research block is keyed by the 'research' generation, so
    saving/editing a paper must bump it (otherwise the block goes stale)."""
    _with_fake_cache(monkeypatch)

    before = neon_cache._cache_generation("research")
    neon_cache.invalidate_blog_cache()
    after = neon_cache._cache_generation("research")

    assert before != after, "editing a paper must refresh the featured-research cache"
