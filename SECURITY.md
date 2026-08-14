# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting — the **Security** tab, then
**Report a vulnerability**. It reaches the maintainer without the report
being public while it is still exploitable, and it needs no address that
might go stale.

Include what you did, what happened, and what you expected.

For something specific to the hosted service rather than to this code,
the contact address is on its [privacy page](https://github.com/tylkokcr/ShortPulse#deploying-the-hosted-shape),
which every deployment publishes as its data controller.

## What this codebase does and doesn't protect

Being explicit is more useful than a list of reassurances.

### Two deployment shapes, two threat models

ShortPulse runs either **self-hosted** (no accounts, no billing, no
database required) or **hosted** (Supabase auth, credits, Postgres). The
code branches on whether a user is authenticated, not on a separate flag,
so the two can't silently diverge.

A self-hosted install has **no authentication at all** and is not meant to
be exposed to the internet. Anyone who can reach the port can create and
read projects. That is the intended behaviour for a tool running on your
own machine — don't put it behind a public IP without putting something in
front of it.

### Hosted deployment

Required before exposing it publicly:

| Setting | Why |
|---|---|
| `REQUIRE_AUTH=true` | Without it an unauthenticated caller is treated as a self-hoster and renders for free. |
| `MEDIA_URL_SECRET` | Unset, each process invents one, so video links break on restart and don't validate across replicas. Generate with `openssl rand -base64 32`. |
| `SUPABASE_URL` | Enables token verification. |
| Custom SMTP | Supabase's built-in mail is capped at 2 messages/hour and has no delivery SLA. |

### How authentication works

Supabase signs access tokens with an asymmetric key (ES256). The backend
verifies them against the project's **public** JWKS, so it holds no auth
secret — there is nothing here worth stealing for that purpose. A token
must have a valid signature from a currently published key, the right
issuer (this project, not somebody else's free Supabase project), the
`authenticated` audience, and an unexpired `exp`. HS256 is deliberately
not accepted: a symmetric algorithm would mean holding a key that can also
*mint* tokens, and accepting it alongside asymmetric keys is the classic
algorithm-confusion foothold.

An invalid token is a 401. It is never downgraded to anonymous, which on a
paid deployment would turn an expired session into free renders.

### Access control

A project row with an owner is reachable **only** by that owner —
reads, listing, deletion, video playback and render progress. The check
keys off the row rather than the caller, so an unauthenticated request can
never reach an owned project. Denials return 404 rather than 403 so
project ids can't be probed for existence.

### Uploaded video

`POST /api/uploads` is the only endpoint that accepts a file. What arrives
there is written to disk and then handed to ffmpeg, so three client-supplied
things are treated as claims rather than facts:

- **The filename.** Discarded outright. The stored path is derived from the
  project id the server minted (`uploads.source_path_for`), so nothing an
  attacker sends reaches the filesystem. Only a small allowlist of container
  extensions is honoured, and anything else becomes `.mp4`.
- **The size.** `Content-Length` is not trusted, and a chunked body may not
  declare one at all. The 200MB cap is enforced against the bytes actually
  arriving, and the partial file is deleted the moment it is exceeded — so a
  client cannot fill the disk by understating its length.
- **The content type.** A `.mp4` extension and a `video/mp4` header cost
  nothing to forge. Acceptance depends on ffprobe finding a decodable video
  stream with a real duration; a renamed archive gets no further.

A rejected upload leaves nothing behind: the project row is deleted, and no
credit is charged, because the charge happens only after the file is on disk
and has been validated.

The stored video is served through the same signed short-lived URLs as
rendered output, so one user's upload is no more reachable than one user's
render.

### Media and WebSocket credentials

A `<video>` tag can't send an `Authorization` header, and neither can a
WebSocket. Both therefore carry a short-lived HMAC token in the URL, the
same mechanism as an S3 presigned link. The token is scoped to one project
and expires in 15 minutes; the project id and the expiry are both inside
the signed payload, so a token can't be replayed against another video or
extended by editing the URL.

Ownership is always checked on the request that *mints* the token — one
that can carry a bearer header — not on the request that serves the bytes.

### Server-side requests

`ProjectConfig.llm.base_url` is an address this server then POSTs the
prompt to. Accepted from the request, it was a server-side fetch to
wherever the caller pointed it — cloud metadata on a deployed host, another
container, an internal admin port — with the response surfacing in the
project's `error` field, so a blind SSRF was readable. Script generation
retries, so one request delivered three.

The whole `llm` block is now replaced at the HTTP boundary with values from
settings, the same rule as `MusicConfig.track_path`: which model writes the
script is a deployment decision, not a per-request one. Only `temperature`
survives, because it changes the writing rather than the destination.

Hosted image generation follows the same rule one step further: the
Replicate token and model live in settings and `ProjectConfig` gains no
field for either, so there is nothing to discard at the boundary and
nothing for a later change to forget. Replicate returns a prediction whose
`urls.get` this server then polls — an address read out of a response body
is the same shape of hazard whoever sent it, so it is checked against the
API's own host prefix before each request.

### Payments

Credits are granted from the Stripe webhook and nowhere else. The success
URL is a page the customer's browser is sent to and anyone can open it, so
granting there would give the product away; the webhook arrives signed.

That makes the signature check load-bearing rather than ceremonial — the
handler adds credits, so an unverified webhook route mints them for
whoever finds the URL. Verification is refused outright when no webhook
secret is configured, rather than falling back to trusting the payload: a
deployment that forgot the secret would otherwise be wide open and look
fine.

What was bought is decided server-side. The browser sends a pack id;
price and credit count are read from the server's own table, never from
the request. The buyer is identified from signed session metadata rather
than from the return URL, which is under their control by the time they
are looking at it.

Stripe retries a delivery until it gets a 2xx, and each retry carries a
new event id — so the ledger's idempotency key is the *checkout session*,
not the event, and the unique index on it is what stops one purchase
paying out twice.

Card details never reach this application.

### Credits

The ledger is append-only; a balance is always `sum(delta)`, never a
stored column that can drift. Debits for one user serialise behind a
per-user advisory lock, so concurrent requests can't both spend the same
credit. Every debit that can be retried carries an idempotency key, and a
project can be refunded at most once — enforced by a partial unique index,
not by application logic.

### Database

Every query uses parameter placeholders. One query — `update_project` —
builds its `SET` clause by interpolation; column names there may only come
from a hardcoded whitelist, and `test_column_names_cannot_be_injected`
fails if that whitelist is removed.

## Known gaps

Currently true, and deliberately listed rather than quietly omitted:

- **Rate limiting is per-process.** Requests are throttled per user (or
  per client address when anonymous), with a separate, much tighter budget
  for starting renders. With several instances the effective limit is
  multiplied by the instance count; moving the counters to Postgres or
  Redis would fix that at the cost of a round trip per request.
- **Renders are not isolated.** FFmpeg and the diffusion models run in the
  API process, with the same filesystem access.
- **A restarting instance fails renders another instance is running.** A
  conditional write stops it corrupting them, but a proper worker lease is
  still missing.
- **Prompts reach a local LLM unfiltered.** There is no moderation on what
  a user can ask for.

## Dependencies

`pip-audit` and `npm audit` both report no known vulnerabilities. Re-check
before each release rather than trusting this line — it was true when
written, which is a different claim.

## How this code was reviewed

It was written with heavy AI assistance, so the review that matters is the
one that doesn't take the code's word for anything:

- Every security property above has a test that **fails when the
  protection is removed** — verified by deliberately breaking each one and
  confirming the suite goes red. A passing test that also passes against
  the broken version proves nothing, and two such tests were caught and
  rewritten during development.
- The auth tests sign with a real ES256 keypair and verify real
  signatures; nothing about the verification itself is mocked.
- Findings that came from probing a running server rather than reading the
  code: the WebSocket ignoring authentication entirely, and anonymous
  listing returning every user's projects. Both looked correct on the
  page.
