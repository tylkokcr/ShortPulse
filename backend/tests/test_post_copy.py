"""Post copy for videos that never had a script."""

from __future__ import annotations

from app.schemas.project import (
    BeatEditSpec,
    CaptionTrack,
    Project,
    ProjectConfig,
    ProjectSource,
    Word,
)
from app.services import post_copy


def test_what_the_model_writes_is_cleaned_and_bounded():
    copy = post_copy.validate(
        {
            "title": '"' + "x" * 150 + '"',
            "description": "d",
            "hashtags": ["#futbol", "neymar ", "#a b!", ""] * 3,
        }
    )
    assert len(copy.title) == 100 and not copy.title.startswith('"')
    assert copy.hashtags[:3] == ["futbol", "neymar", "ab"] and len(copy.hashtags) == 8
    assert post_copy.validate("not json").title == ""


def test_the_prompt_reads_a_file_name_as_words_and_skips_generic_names():
    upload = Project(
        config=ProjectConfig(topic="Neymar_100+_WOW_Skills (2).mp4", source=ProjectSource.UPLOAD),
        captions=CaptionTrack(words=[Word(text="Merhaba", start_ms=0, end_ms=400)]),
    )
    prompt = post_copy.prompt_for(upload, "tr")
    assert "Neymar 100+ WOW Skills" in prompt and "Turkish" in prompt and "Merhaba" in prompt

    edit = Project(
        config=ProjectConfig(
            topic="Beat edit",
            source=ProjectSource.BEAT_EDIT,
            beat_edit=BeatEditSpec(clip_count=3, duration_s=30, style="energetic"),
        )
    )
    prompt = post_copy.prompt_for(edit, "en")
    assert "Beat edit" not in prompt and "cut to music" in prompt and "energetic" in prompt


async def test_the_route_writes_in_the_videos_own_language(monkeypatch):
    from fastapi import FastAPI

    from app.api.routes import projects
    from app.schemas.project import PostCopy
    from app.services import project_store
    from tests.test_uploads import _client

    project_store.configure(None)
    project = await project_store.create_project(
        ProjectConfig(topic="t", source=ProjectSource.UPLOAD, language="tr")
    )
    seen: list[str] = []

    async def suggest(p, lang, llm):
        seen.append(lang)
        return PostCopy(title="Başlık", hashtags=["futbol"])

    monkeypatch.setattr(post_copy, "suggest", suggest)
    app = FastAPI()
    app.include_router(projects.router)
    async with _client(app) as client:
        response = await client.post(f"/api/projects/{project.config.id}/post-copy", json={"lang": "en"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Başlık" and seen == ["tr"]
