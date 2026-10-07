"""Which media URLs authenticate themselves — runs without a database."""

import uuid


def test_my_files_media_paths_carry_their_own_credential():
    """A kept file's stream and poster are fetched by <video> and <img>,
    which send no bearer token — the same 401 as a project's video, found
    the same way, on the live site the day My files shipped. Checked on
    the predicate itself so it runs without a database."""
    from starlette.requests import Request

    from app.api.middleware import _authenticates_itself

    def request(path: str, query: str = "") -> Request:
        return Request({"type": "http", "path": path, "query_string": query.encode(), "headers": []})

    media_id = str(uuid.uuid4())
    assert _authenticates_itself(request(f"/api/media/{media_id}/stream", "token=x"))
    assert _authenticates_itself(request(f"/api/media/{media_id}/poster", "token=x"))
    # Without a token, or anywhere else under /api/media, it stays behind
    # authentication: the listing and the upload are the user's own.
    assert not _authenticates_itself(request(f"/api/media/{media_id}/stream"))
    assert not _authenticates_itself(request("/api/media", "token=x"))
    assert not _authenticates_itself(request(f"/api/media/{media_id}/url", "token=x"))
