-- What came out wrong, said by the person it came out wrong for.
--
-- This is the only channel of its kind here. The privacy page promises no
-- analytics, no tracking pixels and no third-party scripts, and that
-- promise is worth more than anything a vendor SDK would report — so the
-- one honest way to learn whether the output is any good is to ask, and
-- to keep the answer in our own database.
--
-- Scoped to a scene rather than to the product. "How would you rate
-- ShortPulse" produces an average that cannot be acted on; "scene 4 of a
-- photoreal fast_hybrid render was wrong, and here is why" changes what
-- gets built next. It also sits exactly where the fix already lives: the
-- same row offers a re-roll.

create table if not exists feedback (
    id            bigserial primary key,
    -- Null once the project is deleted. The observation outlives the
    -- render it was about, deliberately — see the denormalised columns
    -- below.
    project_id    uuid references projects(id) on delete set null,
    user_id       uuid references app_users(id) on delete set null,
    -- Null means the video as a whole; an integer means that scene.
    scene_index   integer check (scene_index is null or scene_index >= 0),
    rating        text not null check (rating in ('up', 'down')),
    -- A short tag from a fixed list in the UI, so the common cases are
    -- countable without reading prose. Free text goes in `note`.
    reason        text,
    note          text,

    -- Copied at write time rather than joined later, which is the one
    -- place in this schema that duplicates instead of referencing.
    --
    -- The whole value of this table is answering "which mode and style
    -- produce bad scenes", and a join cannot answer it once the project
    -- is gone — which is exactly what a user does with a render they
    -- disliked. Losing the evidence when someone acts on the complaint
    -- would be the worst possible time to lose it.
    visual_mode   text,
    art_style     text,

    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- One verdict per scene per person: changing your mind replaces the old
-- answer instead of appending a second one. Two partial indexes because
-- `scene_index is null` (the whole video) does not compare equal to
-- itself in a plain unique constraint.
create unique index if not exists feedback_one_per_scene_idx
    on feedback (project_id, user_id, scene_index)
    where scene_index is not null;

create unique index if not exists feedback_one_per_project_idx
    on feedback (project_id, user_id)
    where scene_index is null;

-- The query this exists to serve: what is failing, by mode and style.
create index if not exists feedback_rating_idx
    on feedback (rating, visual_mode, art_style, created_at desc);
