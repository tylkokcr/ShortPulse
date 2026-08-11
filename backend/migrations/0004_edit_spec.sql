-- ShortPulse: the edit document for a finished project.
--
-- Captions and text overlays as the user last left them. Kept separate
-- from `config` (what was asked for) and `script` (what was generated):
-- this is what the video currently *is*, and it is the only one of the
-- three a user edits directly.
--
-- Applying it re-runs the burn-in pass alone, so it is cheap enough to be
-- free — see services/editing.py.

alter table projects
    add column if not exists edit jsonb;
