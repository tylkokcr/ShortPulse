-- ShortPulse: a project that produced other projects.
--
-- An extraction reads a long upload's transcript, cuts the stretches that
-- stand up on their own, and makes each cut an ordinary upload project.
-- The parent renders nothing. What it has to show for itself is this
-- column: the ids of what it made, in the order they appear in the source.
--
-- A real text[] rather than JSONB, unlike `script` and `captions` beside
-- it. Those mirror Pydantic models that still change shape and nothing
-- queries inside them; this is a list of ids whose shape cannot change,
-- and being an array means "which extraction made this clip" is a query
-- rather than a scan through blobs.
--
-- Not null with an empty default, so every project that already exists
-- answers the question — a project that produced no clips and a project
-- that could not produce clips are the same thing to every reader here,
-- and neither is null.

alter table projects
    add column if not exists clip_project_ids text[] not null default '{}';
