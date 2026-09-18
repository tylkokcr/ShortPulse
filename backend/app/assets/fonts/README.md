# Caption fonts

Bundled rather than installed, because libass does not report a missing
font — it silently substitutes, and the first anyone knows is a finished
video in the wrong face. Shipping the files and passing `fontsdir` makes
the render deterministic on any machine.

| File | Covers | Licence |
|---|---|---|
| `Montserrat-Bold.ttf` | Latin, Latin-ext, Cyrillic | OFL 1.1 |
| `Anton-Regular.ttf` | Latin, Latin-ext | OFL 1.1 |
| `Bangers-Regular.ttf` | Latin, Latin-ext | OFL 1.1 |
| `PermanentMarker-Regular.ttf` | Latin (no Turkish ğ/ş/ı) | Apache 2.0 |
| `NotoSansArabic-Bold.ttf` | Arabic | OFL 1.1 |

Coverage is measured from each file's cmap, not taken from its listing —
`subtitle_engine.FONT_COVERAGE` holds the result and is what decides
which font a project actually gets. Check it after changing anything
here, or a language quietly starts rendering as empty boxes.

`NotoSansArabic-Bold.ttf` is a static instance cut from the upstream
variable font at `wght=700`: libass renders a variable font at its
default weight, which put Arabic captions in Regular next to everything
else in Bold, and the whole file is 650KB smaller this way.
