-- Where a file in My files came from, and when it goes.
--
-- A file can now arrive from a link rather than from the user's disk. For
-- a YouTube link that matters twice over: the project made from it must
-- not be posted back to YouTube through our API (services/link_import.py
-- explains why), and the downloaded source is not kept — it expires a day
-- after it arrived, long enough to cut it, short enough not to become a
-- library of other people's uploads.

alter table media_files add column if not exists origin text not null default 'upload';
alter table media_files add column if not exists expires_at timestamptz;

alter table media_files drop constraint if exists media_files_origin_check;
alter table media_files add constraint media_files_origin_check
    check (origin in ('upload', 'link', 'youtube'));
