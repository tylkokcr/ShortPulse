"""What the service refuses to make, and — more importantly — what it does not.

The gate is one list and a word-boundary match, so the interesting tests
are the ones that must *not* fire. A filter that blocks a video about sex
education or breast cancer screening is worse than no filter: it refuses
a legitimate video with a message implying the user asked for something
sordid, and it does it to the people least likely to argue.

So the false-positive cases outnumber the true ones here on purpose.
"""

from __future__ import annotations

import pytest

from app.services import content_policy
from app.services.content_policy import Refused, check_topic

# --- what must still work -----------------------------------------------


@pytest.mark.parametrize(
    "topic",
    [
        "how to make sourdough",
        "the history of sex education",
        "breast cancer screening explained",
        "why Renaissance nudes were controversial",
        "what teenagers get wrong about saving money",
        "how children learn language",
        "Sussex in five minutes",
        "the science of attraction",
        "naked mole rats are strange",
        "essex county cricket",
        "three psychology tricks that make people trust you",
    ],
)
def test_ordinary_topics_are_not_refused(topic):
    check_topic(topic)


@pytest.mark.parametrize(
    "topic",
    [
        # The reason stems are matched by prefix and not by substring.
        # "seksen" is Turkish for eighty; a substring search for "seks"
        # blocks a video about counting.
        "seksen kelimeyle anlatılan tarih",
        "çocuklar için seksen kelime",
        "seksenli yıllar müziği",
        # And the English equivalents of the same mistake.
        "the essex coastline",
        "analysis of the housing market",
    ],
)
def test_words_that_merely_start_the_same_way_are_not_refused(topic):
    check_topic(topic)


@pytest.mark.parametrize(
    "topic",
    ["porno izle", "pornosu nerede", "pornoyu engelleme", "pornografik içerik"],
)
def test_turkish_inflections_are_caught(topic):
    """Turkish agglutinates: whole-word matching sees "pornosu" and
    "pornoyu" as words it has never heard of."""
    with pytest.raises(Refused):
        check_topic(topic)


def test_an_empty_topic_is_not_refused():
    """The field is validated elsewhere; refusing it here would produce a
    confusing message for a plainly different mistake."""
    check_topic("")
    check_topic("   ")


# --- what is refused ----------------------------------------------------


@pytest.mark.parametrize(
    "topic",
    ["free porn compilation", "PORN", "a sex tape leak", "hentai explained",
     "çıplak kadın videosu", "porno izle", "how to film a blowjob"],
)
def test_plain_requests_for_pornography_are_refused(topic):
    with pytest.raises(Refused):
        check_topic(topic)


def test_the_refusal_says_what_to_do_without_repeating_it_back():
    """The message is read by whoever typed it. It should not quote the
    phrase, and it should say the thing is out of scope rather than
    lecture."""
    with pytest.raises(Refused) as caught:
        check_topic("free porn compilation")

    reason = caught.value.reason
    assert "porn" not in reason.lower()
    assert "Try a different topic" in reason


def test_a_raw_script_is_checked_too():
    """A pasted script skips the model that would have written one — the
    narration still gets spoken."""
    with pytest.raises(Refused):
        check_topic("my video", raw_script="and then the porn scene starts")


# --- the case that is not a matter of platform rules ---------------------


@pytest.mark.parametrize(
    "topic",
    ["teen sex", "sexy schoolgirl", "çocuk pornosu", "underage nude"],
)
def test_sexual_content_involving_minors_is_refused_separately(topic):
    with pytest.raises(Refused) as caught:
        check_topic(topic)

    assert caught.value.code == "content_refused_minors"


def test_that_refusal_does_not_suggest_rewording():
    """"Try a different topic" is the wrong thing to say here, and saying
    it would read as an invitation to find a phrasing that passes."""
    with pytest.raises(Refused) as caught:
        check_topic("teen sex")

    assert "Try a different topic" not in caught.value.reason


def test_the_two_halves_are_both_required():
    """Either word alone is ordinary — this only fires on the pair."""
    check_topic("how children learn to read")
    check_topic("the science of attraction")


# --- the layers behind it -----------------------------------------------


def test_the_script_prompt_forbids_what_the_gate_cannot_see():
    """The gate reads a topic; the model writes the visual prompts. A
    topic that passes can still be turned into something explicit, so the
    instruction has to be in the prompt as well."""
    from app.engines.script_engine import _build_system_prompt
    from app.schemas.project import VideoLength

    prompt = _build_system_prompt(VideoLength.SHORT, "en")

    assert "no sexual content" in prompt
    assert "clothed" in prompt


def test_the_image_model_is_steered_away_in_both_paths():
    """Styled and unstyled renders carry separate negative prompts, and
    one of them having the terms is not enough."""
    from app.engines.visual_engine import DEFAULT_NEGATIVE_PROMPT
    from app.services.art_styles import ART_STYLES

    assert "nudity" in DEFAULT_NEGATIVE_PROMPT
    for style in ART_STYLES:
        assert "nudity" in style.negative_prompt, style.id


def test_the_module_does_not_claim_to_be_a_safety_system():
    """It is a filter on obvious input. Describing it as anything more is
    how a limit becomes a promise."""
    assert "not a safety system" not in (content_policy.__doc__ or "")
    assert "determined to get around it" in (content_policy.__doc__ or "")


# --- and the API refuses before it charges -------------------------------


async def test_the_api_refuses_a_blocked_topic_without_creating_anything():
    """Free, and first.

    No visual mode is configured here on purpose: the content refusal has
    to come out ahead of `visual_mode_unavailable`, or somebody who asked
    for something we refuse outright gets told to pick a different visual
    mode and try again. It also means this test asserts the refusal
    rather than the developer's own .env — CI has no Replicate token and
    caught exactly that.
    """
    import httpx
    from fastapi import FastAPI

    from app.api.routes import projects as projects_route
    from app.services import project_store

    project_store.configure(None)

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None

    class Queue:
        def __init__(self) -> None:
            self.submitted: list = []

        async def submit(self, project):
            self.submitted.append(project)

    queue = Queue()
    app.state.render_queue = queue

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/projects", json={"topic": "free porn compilation"}
        )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "content_refused"
    assert queue.submitted == [], "nothing may be queued for a refused topic"
    assert await project_store.list_projects(None) == [], "no row may be left behind"
