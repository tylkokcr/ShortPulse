"""The shape every publishing platform is made to fit.

Three platforms, three genuinely different mechanics:

  * **YouTube** takes the bytes. A resumable upload, from this machine to
    theirs, and the response carries the video id.
  * **Instagram** takes a URL, opens a "container" for it, and finishes
    asynchronously — the container has to be polled until it reports
    FINISHED before a second call actually publishes it.
  * **TikTok** also takes a URL, but pulls it on its own schedule and
    reports back through a status endpoint of its own.

So this is not an interface invented in case a fourth backend shows up
one day. It exists because the code that decides *what* to post — which
project, which caption, whose account, whether a human approved it — is
the same for all three, and only the last step differs. Without a seam
here that logic would be written three times and drift twice.

It also happens to be the seam a hosted aggregator would slot into, if the
audits ever prove more trouble than the monthly bill. That is a
consequence of the shape, not the reason for it: nothing here is written
speculatively for a backend that does not exist.

What is deliberately *not* in this interface:

  * Storage. Publishers never touch the database — they are handed
    decrypted tokens and hand back a result, so a publisher cannot be the
    thing that leaks a token into a log or forgets to encrypt one.
  * The attribution rule. Stock footage carries a licence condition that
    the credit appears in the post description, and leaving that to each
    publisher means the third one forgets. It is applied once, in the
    manager, before a target ever reaches here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol


class PublishError(Exception):
    """A publish attempt failed in a way worth showing the user.

    `message` is written for them, not for a log: it ends up in
    social_posts.error and is the only thing they will see. "YouTube
    rejected the title as too long" is one of these; a TypeError is not.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ConnectionRevoked(PublishError):
    """The grant is gone — the user removed access, or it expired beyond
    refreshing. Distinct from a failed post because the connection itself
    is now dead, and the fix is reconnecting rather than retrying."""

    def __init__(self, message: str = "This account is no longer connected.") -> None:
        super().__init__(message, retryable=False)


@dataclass(frozen=True)
class PlatformAccount:
    """Who the tokens belong to, as the platform describes them."""

    external_id: str
    display_name: str | None = None


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    # What was actually granted, which is not always what was asked for.
    # A user can uncheck a permission on Google's consent screen and the
    # flow still completes; the first sign of it should be a clear refusal
    # rather than a 403 partway through an upload.
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PublishTarget:
    """One finished video, ready to go out.

    Both `video_path` and `video_url` are populated for every publish,
    because which one is useless depends on the platform: YouTube ignores
    the URL and reads the file, Instagram and TikTok ignore the file and
    fetch the URL — from the public internet, which is why it is signed
    and time-limited rather than a path.
    """

    video_path: Path
    video_url: str
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)
    # What the user asked for. What they get may be less: an unaudited
    # TikTok client cannot post anything but SELF_ONLY, and an unverified
    # YouTube project cannot post anything but private. The outcome says
    # what actually happened.
    privacy: str = "public"


@dataclass(frozen=True)
class PublishOutcome:
    platform_post_id: str
    url: str | None = None
    # The visibility the platform actually applied. When this differs from
    # what was requested it is not an error and must not be reported as
    # one — but it is the answer to "why isn't my video public", so it is
    # recorded and shown.
    privacy: str = "public"


class SocialPublisher(Protocol):
    """One platform's half of publishing.

    Implementations are stateless and hold only configuration: every call
    is handed the tokens it needs. That keeps them safe to build once at
    startup and share across requests, and it is what lets the manager own
    refresh and storage without each platform reimplementing either.
    """

    platform: str

    def authorize_url(self, state: str) -> str:
        """Where to send the browser to start the grant.

        `state` is opaque here and verified by the caller when it comes
        back — it is what stops a third party from completing somebody
        else's connection flow.
        """
        ...

    async def exchange_code(self, code: str) -> tuple[OAuthTokens, PlatformAccount]:
        """Turn the code from the redirect into tokens, and find out whose
        they are. The account lookup is part of this rather than a
        separate call because a connection with no account id cannot be
        stored — it is half the primary key."""
        ...

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """A fresh access token. Raises ConnectionRevoked when the grant
        is gone, which is the signal to stop retrying and ask the user to
        reconnect."""
        ...

    async def publish(self, tokens: OAuthTokens, target: PublishTarget) -> PublishOutcome:
        """Put the video on the platform. Raises PublishError on anything
        the user should be told about."""
        ...
