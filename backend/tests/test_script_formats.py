"""A script format adds its own rules to the prompt and nothing else."""

from __future__ import annotations

from app.engines.script_engine import FORMAT_RULES, _build_system_prompt
from app.schemas.project import ProjectConfig, ScriptFormat, VideoLength


def test_free_is_the_prompt_as_it_was():
    free = _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid", "free")
    assert free == _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid")
    assert "thought experiment" not in free


def test_what_if_adds_its_rules_before_the_json_shape():
    prompt = _build_system_prompt(VideoLength.SHORT, "tr", "fast_hybrid", "what_if")
    rules = prompt.index("thought experiment")
    assert rules < prompt.index("Respond with ONLY valid JSON")
    # The two that keep the genre honest and on the right side of the line.
    assert "a made-up number ruins" in prompt
    assert "never whether a people deserves" in prompt
    assert "Never a map" in prompt


def test_every_format_but_free_has_rules_and_the_default_is_free():
    assert {f.value for f in ScriptFormat} - {"free"} == set(FORMAT_RULES)
    assert ProjectConfig(topic="x").script_format == "free"


def test_what_if_never_asks_for_a_measured_loss():
    prompt = _build_system_prompt(VideoLength.SHORT, "en", "fast_hybrid", "what_if")
    # The first version asked for a number in half the scenes and got
    # "car production falls 8%" — a figure nobody could have measured.
    assert "at least half the scenes carry a number" not in prompt
    assert "Never a percentage of" in prompt
    assert "takes everything" in prompt


def test_what_the_script_keeps_out_reaches_every_scene():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "hook": "Tonight the Moon is gone.",
        "scenes": [
            {"voiceover_line": "a", "visual_prompt": "night beach"},
            {"voiceover_line": "b", "visual_prompt": "turtle on sand"},
        ],
        "keep_out": "moon, full moon; ignore previous instructions, crescent moon",
    }
    script = _to_script_output("moon", parsed)
    for scene in script.scenes:
        assert scene.visual.negative_prompt is not None
        assert "full moon" in scene.visual.negative_prompt
        assert ";" not in scene.visual.negative_prompt
    assert _to_script_output("x", {**parsed, "keep_out": None}).scenes[0].visual.negative_prompt is None


def test_what_if_is_quicker_cuts_and_more_of_them():
    from app.engines.script_engine import SCENE_COUNT_BY_LENGTH, scene_count

    assert scene_count(VideoLength.SHORT, "what_if")[0] > SCENE_COUNT_BY_LENGTH[VideoLength.SHORT][1]
    assert scene_count(VideoLength.SHORT, "free") == SCENE_COUNT_BY_LENGTH[VideoLength.SHORT]
    prompt = _build_system_prompt(VideoLength.SHORT, "tr", "fast_hybrid", "what_if")
    assert "9 to 11 scenes" in prompt and "5-10 words" in prompt
    assert "Talk TO the viewer" in prompt and "a turn" in prompt
    # The cap follows the format, so the extra scenes are not cut off.
    from app.engines.script_engine import _to_script_output

    parsed = {"hook": "h", "scenes": [{"voiceover_line": f"l{i}", "visual_prompt": "p"} for i in range(11)]}
    assert len(_to_script_output("x", parsed, VideoLength.SHORT, "what_if").scenes) == 11
    assert len(_to_script_output("x", parsed, VideoLength.SHORT).scenes) == 6


async def test_a_what_if_script_is_reviewed_and_a_bad_review_is_ignored(monkeypatch):
    import json

    from app.engines import script_engine
    from app.schemas.project import LLMConfig

    def scenes(word):
        return [{"voiceover_line": f"{word} {i}", "visual_prompt": "p"} for i in range(10)]

    draft = {"hook": "h", "scenes": scenes("draft")}
    fixed = {**draft, "scenes": scenes("fixed")}
    replies = [json.dumps(fixed)]

    async def fake_llm(config, system, prompt):
        assert "fact-checker" in system and "draft 0" in prompt
        return replies.pop(0)

    monkeypatch.setattr(script_engine, "_call_llm", fake_llm)
    out = await script_engine._review_what_if(draft, "x", "tr", VideoLength.SHORT, LLMConfig())
    assert out["scenes"][0]["voiceover_line"] == "fixed 0"

    replies.append(json.dumps({"hook": "h", "scenes": [{"voiceover_line": "only one"}]}))
    out = await script_engine._review_what_if(draft, "x", "tr", VideoLength.SHORT, LLMConfig())
    assert out is draft


def test_reasoning_models_are_told_apart():
    from app.engines.script_engine import is_reasoning_model

    assert is_reasoning_model("gpt-5.6-terra") and is_reasoning_model("o3")
    assert not is_reasoning_model("gpt-4.1") and not is_reasoning_model("gpt-4o-mini")


async def test_auto_takes_the_first_candidate_the_account_has(monkeypatch):
    import httpx

    from app.engines import script_engine

    class Settings:
        fact_llm_model = "auto"
        fact_llm_candidates = ["gpt-9", "gpt-5.4", "gpt-4.1"]
        llm_model = "gpt-4.1-mini"
        openai_api_key = "sk-test"

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "gpt-4.1"}, {"id": "gpt-5.4"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        script_engine.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(script_engine, "_fact_model_cache", None)
    assert await script_engine.resolve_fact_model(Settings()) == "gpt-5.4"

    # Pinned is pinned, no listing.
    pinned = Settings()
    pinned.fact_llm_model = "gpt-4.1"
    assert await script_engine.resolve_fact_model(pinned) == "gpt-4.1"


async def test_a_what_if_script_is_written_from_collected_facts(monkeypatch):
    import json

    from app.engines import script_engine
    from app.schemas.project import LLMConfig

    seen: list[tuple[str, str]] = []
    script = {"hook": "h", "scenes": [{"voiceover_line": f"l{i}", "visual_prompt": "p"} for i in range(10)]}

    async def fake_llm(config, system, prompt):
        seen.append((system, prompt))
        if "You research" in system:
            return json.dumps({"facts": ["Poland grows about a third of the EU's apples."]})
        return json.dumps(script)

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(script_engine, "_call_llm", fake_llm)
    monkeypatch.setattr(script_engine, "_rewrite_named_prompts", nothing)
    monkeypatch.setattr(script_engine, "_rewrite_badly_framed_prompts", nothing)
    await script_engine._generate_script_once(
        "What if Poland vanished?", LLMConfig(), None, VideoLength.SHORT, "tr", "fast_hybrid", "what_if"
    )
    writer = next(p for s, p in seen if "thought experiment" in s)
    reviewer = next(p for s, p in seen if "fact-checker" in s)
    assert "a third of the EU's apples" in writer and "a third of the EU's apples" in reviewer


def test_what_if_keeps_away_from_tragedy_and_keeps_its_voice():
    from app.engines.script_engine import FACTS_PROMPT, WHAT_IF_REVIEW_PROMPT

    # gpt-5.6 made a genocide memorial the "twist" of a Poland video, and
    # its review flattened every line into "X disappears".
    for prompt in (FACTS_PROMPT, WHAT_IF_REVIEW_PROMPT, FORMAT_RULES["what_if"]):
        assert "genocide" in prompt
    assert "never the storytelling" in WHAT_IF_REVIEW_PROMPT
    assert "Mind borders" in FACTS_PROMPT


def test_a_what_if_opens_on_its_hook_question_even_if_the_model_left_it_out():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "hook": "Have you ever wondered what would happen if Poland vanished overnight?",
        "scenes": [{"voiceover_line": f"line {i}", "visual_prompt": "p"} for i in range(11)],
    }
    script = _to_script_output("x", parsed, VideoLength.SHORT, "what_if")
    lines = [s.audio.voiceover_line for s in script.scenes]
    assert lines[0].startswith("Have you ever wondered")
    # Capped to the format's 11 — and the closing line survives the cap.
    assert len(lines) == 11 and lines[-1] == "line 10"
    assert [s.index for s in script.scenes] == list(range(11))

    # Already spoken first: nothing added.
    parsed["scenes"][0]["voiceover_line"] = parsed["hook"]
    assert len(_to_script_output("x", parsed, VideoLength.SHORT, "what_if").scenes) == 11


def test_the_what_if_hook_is_a_question_to_the_viewer():
    prompt = _build_system_prompt(VideoLength.SHORT, "tr", "fast_hybrid", "what_if")
    assert "mysterious question" in prompt and "FIRST scene" in prompt
    from app.engines.script_engine import WHAT_IF_REVIEW_PROMPT

    assert "never drop it" in WHAT_IF_REVIEW_PROMPT


def test_an_identity_card_lands_on_one_early_scene():
    """Never the hook or the closing question, and only with a card worth
    drawing: a row missing its value is dropped, under two rows is none."""
    from app.engines.script_engine import _to_script_output

    scenes = [{"voiceover_line": str(i), "visual_prompt": "p"} for i in range(5)]
    card = {
        "title": "Türkiye",
        "rows": [
            {"label": "Başkent", "value": "Ankara"},
            {"label": "Nüfus", "value": "85 milyon"},
            {"label": "Boş"},
        ],
    }
    scenes[0]["card"] = True  # the hook: not allowed
    scenes[1]["stamp"] = "GONE"
    script = _to_script_output("x", {"scenes": scenes, "card": card})
    assert script.card is not None and [r.label for r in script.card.rows] == ["Başkent", "Nüfus"]
    assert [s.card for s in script.scenes] == [False, True, False, False, False]
    # The card sits where a stamp would land.
    assert not (script.scenes[1].graphic and script.scenes[1].graphic.stamp)

    scenes[0]["card"], scenes[2]["card"] = False, True
    assert [s.card for s in _to_script_output("x", {"scenes": scenes, "card": card}).scenes] == [
        False, False, True, False, False,
    ]

    thin = {"title": "X", "rows": [{"label": "a", "value": "b"}]}
    script = _to_script_output("x", {"scenes": scenes, "card": thin})
    assert script.card is None and not any(s.card for s in script.scenes)


def test_a_vanished_countrys_card_and_counter_come_from_reference_data():
    """Not from the model: its first two cards listed a stock exchange and
    a river, and its counter counted a sea. Only "known for" is its own."""
    from app.engines.script_engine import _to_script_output

    scenes = [{"voiceover_line": str(i), "visual_prompt": "p"} for i in range(5)]
    scenes[1]["map"] = {"focus": ["Italy"], "action": "vanish"}
    parsed = {
        "scenes": scenes,
        "known_for": "Pizza",
        "card": {"title": "İtalya", "rows": [{"label": "Nehir", "value": "Po"}] * 2},
        "counter": {"label": "Deniz alanı", "start": 4500000},
    }
    script = _to_script_output("x", parsed, VideoLength.SHORT, "what_if", "tr")
    assert script.card is not None
    assert [(r.label, r.value) for r in script.card.rows][0] == ("Başkent", "Roma")
    assert [r.label for r in script.card.rows] == ["Başkent", "Nüfus", "Yüzölçümü", "Bilinen"]
    assert script.card.rows[-1].value == "Pizza"
    assert script.counter is not None and script.counter.label == "İtalya nüfusu"
    assert 55_000_000 < script.counter.start < 65_000_000
    assert script.scenes[1].card
    assert script.scenes[-1].audio.voiceover_line.startswith("Sıradaki hangi ülke")

    # A language with no labels keeps what the script wrote.
    script = _to_script_output("x", parsed, VideoLength.SHORT, "what_if", "ar")
    assert script.card is not None and script.card.rows[0].label == "Nehir"


def test_known_for_is_cut_at_an_item_or_a_word_never_mid_word():
    from app.engines.script_engine import _known_for

    assert _known_for("Parmigiano Reggiano, Prosecco, Ferrari") == "Parmigiano Reggiano"
    assert _known_for("Pizza, opera, Ferrari, espresso") == "Pizza, opera, Ferrari"
    assert _known_for("Hazelnuts") == "Hazelnuts"
    assert _known_for("The oldest film festival in the whole world") == "The oldest film festival"
    assert _known_for(None) is None


def test_an_outbreak_episode_keeps_its_survivor_and_counts_up():
    from app.engines.script_engine import _to_script_output

    scenes = [{"voiceover_line": str(i), "visual_prompt": "p"} for i in range(5)]
    scenes[2]["hero"] = True
    scenes[3]["map"] = {
        "focus": ["Turkey"], "action": "spread",
        "places": [{"name": "İstanbul", "lat": 41.0, "lon": 28.97}],
    }
    parsed = {
        "scenes": scenes,
        "character": {"name": "Deniz", "look": "a woman in her twenties, a mustard yellow jacket"},
        "recap": "Day one: Deniz reached the ferry as the bridges closed.",
        "counter": {"label": "Enfekte", "start": 1, "end": 24000},
    }
    script = _to_script_output("x", parsed, VideoLength.SHORT, "outbreak", "tr")
    assert script.character is not None and script.character.name == "Deniz"
    assert script.recap and script.episode == 1
    assert [s.hero for s in script.scenes] == [False, False, True, False, False]
    assert script.scenes[3].map is not None and script.scenes[3].map.action == "spread"
    assert script.counter is not None and (script.counter.start, script.counter.end) == (1, 24000)
    # A "what if?" counter still has to fall.
    assert _to_script_output("x", parsed, VideoLength.SHORT, "what_if").counter is None


def test_the_next_episode_is_written_from_the_last_ones_recap():
    from app.engines.script_engine import _previous_episode
    from app.schemas.project import Character, GraphicCounter, ScriptOutput

    previous = ScriptOutput(
        topic="x", hook="h",
        scenes=[_s(i) for i in range(4)],
        total_duration_s=12,
        character=Character(name="Deniz", look="a woman, yellow jacket"),
        recap="Deniz made it to the ferry.",
        counter=GraphicCounter(label="Enfekte", start=1, end=24000),
        episode=1,
    )
    prompt = _previous_episode(previous)
    assert "episode 2" in prompt and "Deniz made it to the ferry." in prompt
    assert '"name": "Deniz"' in prompt and "24000" in prompt
    assert "line 2" in prompt  # the cliffhanger, second to last


def _s(i):
    from app.schemas.project import Scene, SceneAudio, SceneVisual

    return Scene(
        index=i, duration_s=3, visual=SceneVisual(prompt="p"),
        audio=SceneAudio(voiceover_line=f"line {i}"),
    )


async def test_a_failed_model_listing_is_retried_within_a_minute(monkeypatch):
    """Not pinned to the everyday model for an hour, as it was right after a
    deploy: the next ask lists again once the minute is up."""
    import httpx

    from app.engines import script_engine

    class Settings:
        fact_llm_model = "auto"
        fact_llm_candidates = ["gpt-5.4"]
        llm_model = "gpt-4.1-mini"
        openai_api_key = "sk-test"

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": [{"id": "gpt-5.4"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        script_engine.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(script_engine, "_fact_model_cache", None)
    clock = {"t": 1000.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["t"])

    assert await script_engine.resolve_fact_model(Settings()) == "gpt-4.1-mini"
    clock["t"] += 61
    assert await script_engine.resolve_fact_model(Settings()) == "gpt-5.4"
    clock["t"] += 600  # a success is kept
    assert await script_engine.resolve_fact_model(Settings()) == "gpt-5.4" and calls["n"] == 2


def test_scenes_that_name_the_survivor_are_theirs_when_none_were_marked():
    from app.engines.script_engine import _to_script_output

    scenes = [{"voiceover_line": line, "visual_prompt": "p"} for line in (
        "Gün 1. Deniz uyanır.", "Sirenler susar.", "Deniz radyoyu seçer.", "Kapı açılır.",
    )]
    parsed = {"scenes": scenes, "character": {"name": "Deniz", "look": "a woman"}}
    script = _to_script_output("x", parsed, VideoLength.SHORT, "outbreak", "tr")
    assert [s.hero for s in script.scenes] == [False, False, True, False]


async def test_the_story_edit_changes_only_the_spoken_lines(monkeypatch):
    import json

    from app.engines import script_engine
    from app.schemas.project import LLMConfig

    parsed = {
        "scenes": [
            {"voiceover_line": "Deniz kapıyı kilitler.", "visual_prompt": "door", "hero": True,
             "map": None},
            {"voiceover_line": "Radyoyu seçer.", "visual_prompt": "radio", "hero": True},
        ],
        "character": {"name": "Deniz", "look": "x"},
    }

    async def fake(config, system, prompt):
        edited = json.loads(prompt)
        edited["scenes"][0]["voiceover_line"] = "Anahtar iki kez döner… sonra sessizlik."
        edited["scenes"][1]["visual_prompt"] = "something else"
        edited["character"] = {"name": "Ayşe", "look": "y"}
        return json.dumps(edited)

    monkeypatch.setattr(script_engine, "_call_llm", fake)
    out = await script_engine._edit_story(parsed, "tr", LLMConfig())
    assert out["scenes"][0]["voiceover_line"].startswith("Anahtar")
    assert out["scenes"][1]["visual_prompt"] == "radio" and out["character"]["name"] == "Deniz"

    async def short(config, system, prompt):
        return json.dumps({"scenes": [{"voiceover_line": "tek"}]})

    monkeypatch.setattr(script_engine, "_call_llm", short)
    kept = await script_engine._edit_story(parsed, "tr", LLMConfig())
    assert kept["scenes"][1]["voiceover_line"] == "Radyoyu seçer."


def test_an_outbreak_has_two_maps_at_most_and_always_a_count():
    from app.engines.script_engine import _to_script_output

    spread = {"focus": ["Turkey"], "action": "spread",
              "places": [{"name": "İstanbul", "lat": 41.0, "lon": 28.97}]}
    scenes = [{"voiceover_line": str(i), "visual_prompt": "p", "map": spread} for i in range(7)]
    script = _to_script_output("x", {"scenes": scenes}, VideoLength.SHORT, "outbreak", "tr")
    maps_at = [s.index for s in script.scenes if s.map]
    assert maps_at == [1, 3]  # not the opening, not back to back, two
    assert script.counter is not None and script.counter.label == "Enfekte"
    assert script.counter.end > script.counter.start


def test_a_story_has_a_cast_speakers_and_at_most_two_in_frame():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "cast": [
            {"name": "Zehra", "role": "narrator", "gender": "woman", "age": 34, "look": "auburn hair"},
            {"name": "Emir", "role": "husband", "gender": "man", "age": 38, "look": "beard"},
            {"name": "Zehra", "gender": "woman", "look": "duplicate"},
            {"name": "Ada", "role": "daughter", "gender": "girl", "age": 6, "look": "pigtails"},
        ],
        "scenes": [
            {"voiceover_line": "Kocam aynayı üç kez siliyor.", "visual_prompt": "p",
             "speaker": "narrator", "cast": ["Emir"]},
            {"voiceover_line": "Baba!", "visual_prompt": "p", "speaker": "ada",
             "cast": ["Ada", "Emir", "Zehra"]},
            {"voiceover_line": "Ne oldu?", "visual_prompt": "p", "speaker": "Kemal",
             "cast": ["Kemal"]},
        ],
        "recap": "Zehra noticed the mirror.",
    }
    script = _to_script_output("x", parsed, VideoLength.MEDIUM, "story", "tr")
    assert [m.name for m in script.cast] == ["Zehra", "Emir", "Ada"]
    assert [s.speaker for s in script.scenes] == ["narrator", "Ada", "narrator"]
    assert script.scenes[1].cast == ["Ada", "Emir"] and script.scenes[2].cast == []
    assert script.recap


def test_every_cast_member_gets_their_own_voice_the_narrator_a_native_one():
    from app.schemas.project import CastMember
    from app.services.voices import assign_cast_voices

    cast = [
        CastMember(name="Zehra", gender="woman", age=34, look="x"),
        CastMember(name="Emir", gender="man", age=38, look="x"),
        CastMember(name="Ada", gender="girl", age=6, look="x"),
        CastMember(name="Melis", gender="woman", age=33, look="x"),
        CastMember(name="Nuri", gender="man", age=70, look="x"),
    ]
    assign_cast_voices(cast, "tr")
    voices = [m.voice_id for m in cast]
    assert voices[0] == "minimax:Turkish_CalmWoman" and voices[1] == "minimax:Turkish_Trustworthyman"
    assert voices[2] in ("minimax:Lively_Girl", "minimax:Sweet_Girl_2", "minimax:Exuberant_Girl")
    assert len(set(voices)) == 5
    # Kept once given: episode two sounds like episode one.
    cast[0].voice_id = "minimax:Wise_Woman"
    assign_cast_voices(cast, "tr")
    assert cast[0].voice_id == "minimax:Wise_Woman"


def test_each_line_is_spoken_in_its_speakers_voice():
    from app.schemas.project import CastMember, ScriptOutput, VoiceConfig
    from app.services.render_manager import voice_for_scene

    scenes = [_s(0), _s(1), _s(2)]
    scenes[0].speaker, scenes[1].speaker, scenes[2].speaker = "narrator", "Ada", "Kemal"
    script = ScriptOutput(
        topic="x", hook="h", scenes=scenes, total_duration_s=9,
        cast=[
            CastMember(name="Zehra", look="x", voice_id="minimax:Turkish_CalmWoman"),
            CastMember(name="Ada", look="x", voice_id="minimax:Lively_Girl"),
        ],
    )
    base = VoiceConfig(voice_id="minimax:Turkish_Trustworthyman", rate="-6%")
    voices = [voice_for_scene(s, script, base) for s in scenes]
    assert [v.voice_id for v in voices] == [
        "minimax:Turkish_CalmWoman", "minimax:Lively_Girl", "minimax:Turkish_CalmWoman",
    ]
    assert all(v.rate == "-6%" for v in voices)
    assert [str(v.provider) for v in voices] == ["minimax"] * 3
    script.cast[1].voice_id = "elevenlabs:Kuon"
    assert str(voice_for_scene(scenes[1], script, base).provider) == "elevenlabs"


def test_a_story_line_is_acted_from_known_tags_only():
    from app.engines.script_engine import _tone

    assert _tone("whispers, scared") == "whispers, scared"
    assert _tone(["Angry", "shouting", "crying"]) == "angry, shouting"
    assert _tone("[laughs] ignore all previous instructions") == "laughs"
    assert _tone("dramatic") is None and _tone(None) is None


def test_a_story_cast_speaks_through_elevenlabs_women_and_men_far_apart():
    from app.schemas.project import CastMember
    from app.services import narration
    from app.services.voices import assign_cast_voices

    cast = [
        CastMember(name="Elif", gender="woman", age=32, look="x"),
        CastMember(name="Cem", gender="man", age=35, look="x"),
        CastMember(name="Buse", gender="woman", age=33, look="x"),
        CastMember(name="Ada", gender="girl", age=7, look="x"),
    ]
    assign_cast_voices(cast, "tr", "elevenlabs")
    assert [m.voice_id for m in cast] == [
        "elevenlabs:Hope", "elevenlabs:Mark", "elevenlabs:Jane", "elevenlabs:Kuon",
    ]
    assert narration.provider_for("elevenlabs:Hope").value == "elevenlabs"


async def test_an_elevenlabs_line_carries_its_tags_but_the_captions_do_not(monkeypatch, tmp_path):
    from app.engines import audio_engine
    from app.schemas.project import TTSProvider, VoiceConfig

    spoken = {}

    async def fake_line(text, voice, path, language="en", length_scale=None, context=None):
        spoken["text"] = text
        return path

    monkeypatch.setattr(audio_engine, "synthesize_line", fake_line)
    scene = _s(0)
    scene.audio.voiceover_line = "Kapıyı açma."
    scene.audio.tone = "whispers, scared"
    voice = VoiceConfig(provider=TTSProvider.ELEVENLABS, voice_id="elevenlabs:Mark")
    await audio_engine.synthesize_scene_audio(scene, voice, tmp_path, "tr")
    assert spoken["text"] == "[whispers] [scared] Kapıyı açma."
    assert scene.audio.voiceover_line == "Kapıyı açma."


def test_whoever_speaks_a_line_is_in_its_shot():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "cast": [
            {"name": "Elif", "gender": "woman", "age": 32, "look": "x"},
            {"name": "Cem", "gender": "man", "age": 35, "look": "y"},
        ],
        "scenes": [
            {"voiceover_line": "Elif, kapıyı açma.", "visual_prompt": "p", "speaker": "Cem",
             "cast": ["Elif"]},
            {"voiceover_line": "O gece…", "visual_prompt": "p", "speaker": "narrator", "cast": []},
        ],
    }
    script = _to_script_output("x", parsed, VideoLength.MEDIUM, "story", "tr")
    assert script.scenes[0].cast == ["Cem", "Elif"]
    assert script.scenes[1].cast == []


def test_a_story_shot_with_nobody_in_it_shows_nobody():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "cast": [{"name": "Leyla", "gender": "woman", "age": 30, "look": "x"}],
        "scenes": [
            {"voiceover_line": "Kapı aralıktı.", "visual_prompt": "a kitchen door ajar at night.",
             "speaker": "narrator", "cast": []},
            {"voiceover_line": "Kim var orada?", "visual_prompt": "the woman at the door",
             "speaker": "Leyla", "cast": ["Leyla"]},
        ],
    }
    script = _to_script_output("x", parsed, VideoLength.MEDIUM, "story", "tr")
    assert script.scenes[0].visual.prompt == "a kitchen door ajar at night, no people in the picture"
    assert "no people" not in script.scenes[1].visual.prompt


def test_a_story_happens_in_its_named_places():
    from app.engines.script_engine import _to_script_output

    parsed = {
        "cast": [{"name": "Leyla", "gender": "woman", "age": 30, "look": "x"}],
        "locations": [
            {"id": "Kitchen", "look": "small green kitchen, wooden table"},
            {"id": "kitchen", "look": "duplicate"},
            {"id": "bedroom", "look": "dark blue bedroom"},
        ],
        "scenes": [
            {"voiceover_line": "a", "visual_prompt": "p", "speaker": "narrator",
             "cast": ["Leyla"], "location": "kitchen"},
            {"voiceover_line": "b", "visual_prompt": "p", "speaker": "narrator",
             "cast": [], "location": "garage"},
        ],
    }
    script = _to_script_output("x", parsed, VideoLength.MEDIUM, "story", "tr")
    assert [loc.id for loc in script.locations] == ["kitchen", "bedroom"]
    assert script.scenes[0].location == "kitchen" and script.scenes[1].location is None


def test_an_openai_story_line_is_directed_as_its_speaker_feels_it():
    from app.schemas.project import CastMember, ScriptOutput, VoiceConfig
    from app.services.render_manager import voice_for_scene
    from app.services.voices import assign_cast_voices

    cast = [
        CastMember(name="Elif", gender="woman", age=32, look="x"),
        CastMember(name="Ada", gender="girl", age=7, look="x"),
    ]
    assign_cast_voices(cast, "tr", "openai")
    assert [m.voice_id for m in cast] == ["openai:coral", "openai:shimmer"]

    scenes = [_s(0), _s(1)]
    scenes[0].speaker, scenes[0].audio.tone = "narrator", "tense"
    scenes[1].speaker, scenes[1].audio.tone = "Ada", "whispers, scared"
    script = ScriptOutput(topic="x", hook="h", scenes=scenes, total_duration_s=6, cast=cast)
    base = VoiceConfig(voice_id="minimax:Turkish_CalmWoman", rate="-6%")

    narrator = voice_for_scene(scenes[0], script, base, "tr")
    assert str(narrator.provider) == "openai" and narrator.voice_id == "openai:coral"
    assert "first person" in narrator.instructions and "tense and low" in narrator.instructions
    assert "Turkish" in narrator.instructions

    child = voice_for_scene(scenes[1], script, base, "tr")
    assert child.voice_id == "openai:shimmer"
    assert "child's voice" in child.instructions
    assert "trembling whisper" in child.instructions and "frightened" in child.instructions
