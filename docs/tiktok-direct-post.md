# TikTok direct posting: switching it on and getting it audited

ShortPulse sends TikTok a **draft** by default (the inbox endpoint,
`video.upload`): the video lands in the TikTok app's inbox and the creator
captions and posts it there. With `TIKTOK_DIRECT_POST=true` the publish panel
can also **post it outright** (`video.publish`) — with the caption already
filled in — through a form built to TikTok's Content Posting API UX
guidelines (`frontend/components/render/TikTokComposer.tsx`).

Until TikTok audits the app, every direct post is forced to **Only me
(SELF_ONLY)** and at most five creators can post in 24 hours. That is enough
to record the demo the audit asks for.

## 1. Developer portal

In <https://developers.tiktok.com> → your app:

1. **Products → Content Posting API**: turn on **Direct Post**.
2. **Scopes**: make sure `video.publish` is added, next to `user.info.basic`
   and `video.upload`.
3. **URL properties**: `shortpulse.app` must stay verified. TikTok fetches
   the video from our signed URL (`PULL_FROM_URL`), and an unverified domain
   fails every post with `url_ownership_unverified`.

## 2. Server

Add one line to `backend/.env` on the server, then rebuild:

```
TIKTOK_DIRECT_POST=true
```

```
cd /opt/shortpulse && git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Then, in ShortPulse → Connections, **disconnect and reconnect TikTok**. An
existing connection was granted without `video.publish`, so it keeps sending
drafts until it is connected again.

## 3. What the form does (and why)

Each point is a TikTok requirement for `video.publish`:

| Requirement | In ShortPulse |
|---|---|
| Show which account the post goes to | "Posting to *nickname* @username", from `creator_info` |
| Privacy from the creator's own options, **no default** | Select starts at "Choose…"; posting stays disabled until one is picked |
| Comment / Duet / Stitch chosen by the user, off by default | Three unticked boxes; any the creator has turned off in TikTok are greyed out and say so |
| Commercial content disclosure | "Disclose video content" (off). When it is on, "Your brand" and/or "Branded content" must be ticked, and the label TikTok applies is shown ("Promotional content" / "Paid partnership") |
| Branded content can't be private | "Only you" is disabled while branded content is ticked; the server refuses the combination too |
| Music Usage Confirmation (and Branded Content Policy) | Linked consent line under the form, right where the button is |
| Respect the creator's max video length | Posting is disabled with a message when the video is longer than `max_video_post_duration_sec` |
| The user sees and can edit the caption | Title, description and hashtags above the form; the exact caption TikTok receives is previewed |
| Tell the user the post takes time | After posting: "it can take a few minutes to appear on your profile" |
| AI-generated content | Videos made from a topic are sent with `is_aigc: true`, and the form says they will be labelled |
| No posting without the user | Direct posts only start from this form. Automatic publishing still sends drafts |

## 4. Demo video for the audit

Record the screen in one take, about 1–2 minutes, in English:

1. Open shortpulse.app, sign in, and open a finished video's page.
2. In "Publish this video", show that the title, description and hashtags are
   editable. Press **Suggest** once.
3. Press **Post** next to TikTok. The form opens with the account name.
4. Open the privacy select to show the options and that none is preselected.
   Pick one.
5. Tick **Comment**. Point at a greyed-out interaction if the account has one
   turned off.
6. Turn on **Disclose video content**. Show "Your brand" and "Branded
   content", the label text, and that "Only you" becomes unavailable with
   branded content. Turn disclosure off again.
7. Point at the Music Usage Confirmation line, then press **Post to TikTok**.
8. Show the "processing" message, then switch to the TikTok app or website
   and show the posted video on the profile (it will be private before the
   audit).

## 5. Audit application text (draft)

- **What the app does:** ShortPulse makes short vertical videos: from a
  topic, from a user's own footage (captioned or dubbed), or as an edit of the
  user's clips cut to music. Creators publish a finished video to their own
  TikTok account from the video's page.
- **How Content Posting API is used:** Only when the creator presses "Post to
  TikTok". Before posting they see the target account (creator_info). They
  choose the privacy level from that account's options, with no default, and
  choose the comment/duet/stitch settings. They disclose commercial content
  when it applies. The Music Usage Confirmation and Branded Content Policy
  are shown before posting. Videos are uploaded with PULL_FROM_URL from our
  verified domain. Automatic publishing only ever sends inbox drafts.
- **Scopes:** `user.info.basic` (show which account is connected),
  `video.upload` (drafts to the inbox), `video.publish` (direct posting from
  the form above).
- **Privacy policy / Terms:** https://shortpulse.app/privacy (it has a
  "TikTok user data" section) and https://shortpulse.app/terms. Both already
  name the operator, which reviewers check for.
