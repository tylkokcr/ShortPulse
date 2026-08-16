# Bundled background music

Every track here comes from a source that permits commercial use. Two of
them go further and require nothing in return; the rest are credited below
anyway, because a credit costs nothing and a licence audit costs a lot.

Tracks are transcoded to 96kbps mono before being committed. They play
ducked under a voiceover and loop to fit, so the bitrate is inaudible in
use and the difference is 267MB of originals against 82MB in the image.

## Airport Lounge — the default

**Airport Lounge** by Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 3.0
http://creativecommons.org/licenses/by/3.0/
Source: https://archive.org/details/Incompetech

**Attribution is required for this one.** It is the fallback used whenever
`MusicConfig.enabled` is true and a request supplies no track of its own
(`DEFAULT_MUSIC_TRACK` in `app/core/config.py`), so it can end up in a
video without anyone choosing it. Keep this section as long as the file is
here.

## `atmospheric/` — John Bartmann

Eight cues from *100 Ambient Atmospheric Soundtracks*.
https://johnbartmann.com — released into the public domain (CC0).
No attribution required; listed because the work deserves it.

## `lofi/` and part of `upbeat/` — HoliznaCC0 and Loyalty Freak Music

**HoliznaCC0** — eleven lo-fi tracks. CC0 / public domain.
**Loyalty Freak Music** — eight tracks from *POSITIVE ATTITUDE!*. The files
carry `copyright=Public Domain: http://creativecommons.org/licenses/publicdomain/`
in their own ID3 tags, which is the only licence claim in this directory
that can be verified without leaving the repository.
Both are on the Free Music Archive.

## The rest — Pixabay

Fourteen tracks by alex morgan, fassounds, leberch, arpmedia,
absolutesound, atlasaudio, joyinsound, the_mountain and others, downloaded
under the Pixabay Content License: free for commercial use, no attribution
required, redistribution as a standalone audio file is not.

Bundling them inside a video generator is the intended use. Re-hosting the
directory as a music library would not be.

## Why these are in git, when the example videos are not

`frontend/public/examples/*.mp4` is gitignored and its README explains
why — 26MB of binaries that churn on every re-encode. The same reasoning
applied here would remove 85MB, and it would be wrong.

The difference is who the files are for. The examples are marketing: they
exist to be watched on one website, and a clone that lacks them still runs
the product. The music is the product. A self-hoster who clones this repo
and runs `docker compose up` gets a working video generator, and a working
video generator has music in it — an empty picker is a broken install, not
a missing nicety. That is most of what the MIT licence is offering.

The cost is real and paid once: clones are 85MB heavier, and a push that
adds tracks can time out against GitHub over HTTPS. If it does, the error
is `send-pack: unexpected disconnect while reading sideband packet`, which
looks like a network fault and is a buffer default:

```bash
git config http.postBuffer 524288000
```

Decided deliberately, so: do not "clean this up" without replacing what it
gives a self-hoster.

## If you swap these out

The catalog is the directory — `app/api/routes/music.py` reads whatever is
here at request time, and a subfolder is a mood. Delete a file and it
disappears from the picker; add one and it appears. Keep this file honest
when you do, and delete a section along with the tracks it covers.
