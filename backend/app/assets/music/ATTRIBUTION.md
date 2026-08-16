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

## If you swap these out

The catalog is the directory — `app/api/routes/music.py` reads whatever is
here at request time, and a subfolder is a mood. Delete a file and it
disappears from the picker; add one and it appears. Keep this file honest
when you do, and delete a section along with the tracks it covers.
