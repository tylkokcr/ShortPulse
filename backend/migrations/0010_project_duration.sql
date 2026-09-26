-- How long the finished video is.
--
-- The library lists projects by title, frame and cost, and could not say
-- how long any of them were — the only record of that was
-- `script.total_duration_s` for a generated render and nothing at all for
-- an upload, and `script` is deliberately left out of the listing query
-- (it is the largest column and the list shows none of it).
--
-- So: its own column, written once when the render finishes, next to
-- `credits_cost` which exists for exactly the same reason — a small fact
-- about the outcome that the list needs and the blobs bury.
--
-- Null, not zero, for every project that predates this and for anything
-- that never produced a video: an extraction holds clips rather than
-- footage, and a failed render has no length. The card shows what it has.

alter table projects
    add column if not exists duration_s real;
