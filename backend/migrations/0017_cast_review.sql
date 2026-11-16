-- A story series stops after its script and cast are drawn, for the owner
-- to look at the people before the episode is made ("review"). Re-run on
-- every start like the others: drop and re-add is idempotent.

alter table projects drop constraint if exists projects_status_check;
alter table projects add constraint projects_status_check
    check (status in ('draft', 'rendering', 'review', 'complete', 'failed'));
