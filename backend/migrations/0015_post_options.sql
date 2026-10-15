-- What the user chose for one post beyond its words, for the platforms
-- that ask.
--
-- TikTok's direct posting is the first: who can see it, whether comments,
-- duets and stitches are allowed, and whether it is commercial content —
-- all chosen by the person in the publish panel for that post, with no
-- defaults, which is TikTok's condition for the scope. They are decided
-- when the post is queued and read when a worker sends it, so they are
-- stored with it. NULL is a post with nothing extra, which is every post
-- before this and every post to the other platforms.

alter table social_posts add column if not exists options jsonb;
