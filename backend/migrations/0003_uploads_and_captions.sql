-- ShortPulse: user-uploaded source video + an editable caption track.
--
-- Two things this makes possible that weren't before:
--
--   * A project whose video didn't come from the pipeline. `source_path`
--     points at what the user uploaded; the pipeline is skipped and only
--     the captioning and burn-in steps run.
--
--   * Correcting captions without re-rendering. `captions` holds the words
--     in absolute time against the finished video, so an edit reburns them
--     in one ffmpeg pass instead of re-running the LLM, TTS and visuals.
--
-- Both stay JSONB/text for the same reason `config` and `script` do: they
-- mirror Pydantic models that still change shape, and nothing queries
-- inside them.

alter table projects
    add column if not exists source_path text,
    add column if not exists captions    jsonb;

-- The pipeline writes `config.source`, which is inside the JSONB blob.
-- This partial index exists so "show me my uploads" stays cheap without
-- promoting it to a real column while the shape is still settling.
create index if not exists projects_uploads_idx
    on projects (user_id, created_at desc)
    where source_path is not null;
