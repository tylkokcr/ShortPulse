"""Art styles for the locally generated visual modes.

Every style is deliberately non-photoreal apart from the default. That is a
quality decision, not a taste one: diffusion draws extremities and on-screen
text badly, and a stylized frame absorbs those failures (a cel-shaded hand
with four fingers reads as drawing shorthand) where a photoreal one
advertises them.

Faces used to be on that list and are not any more — the hosted backend
generates on RealVisXL, where they hold up. The reasoning above survives
because it never rested on faces: hands, feet and awkward crops are what
a style hides.

Two things were established by rendering them rather than by reasoning:

  * **The style has to lead the prompt.** Appended as a suffix, "3D Toon"
    and "Claymation" came back as ordinary photographs — the default
    checkpoint is a photorealism fine-tune and simply ignored a trailing
    hint. Moving the style to the front of the prompt fixed both outright.
    Hence a template per style rather than a suffix.
  * **Each style needs its own negative prompt.** The shared one suppresses
    "cgi, 3d render, illustration", which is exactly what a stylized render
    has to produce.

Style names are generic on purpose. The obvious crowd-pleasers ("Lego",
"Disney Toon", "GTA V", "Minecraft") are other companies' trademarks, and
shipping a button that promises to imitate them is not a fight worth
picking.
"""

from __future__ import annotations

from dataclasses import dataclass

# Shared across every style: anatomy and quality failures nobody wants,
# whatever the aesthetic.
_BASE_NEGATIVE = (
    "deformed, distorted, disfigured, extra limbs, extra hands, extra fingers, "
    "bad anatomy, mutated, malformed, low quality, blurry, "
    # Feet were missing while fingers were covered, and a bath scene came
    # back as a melted foot over a tub edge — the one frame in a paid
    # render that made the whole video unusable. The framing rule in
    # script_engine is the real fix; these are the backstop for when the
    # model puts an extremity in shot anyway.
    "deformed feet, extra toes, malformed limbs, "
    "text overlay, watermark, signature"
)

# Pushes a stylized render away from photography, which the photoreal-tuned
# default checkpoint drifts back toward given any excuse.
_ANTI_PHOTO = "photograph, photorealistic, realistic skin pores, dslr, live action"


@dataclass(frozen=True)
class ArtStyle:
    id: str
    name: str
    description: str
    #: Must contain `{prompt}`. Styles put it late so the look leads.
    prompt_template: str
    negative_prompt: str
    #: Filename of the sample frame in frontend/public/art-styles.
    sample: str

    def build_prompt(self, prompt: str) -> str:
        return self.prompt_template.format(prompt=prompt)


ART_STYLES: tuple[ArtStyle, ...] = (
    ArtStyle(
        id="photoreal",
        name="Photoreal",
        description="Looks like footage. Best for objects and scenery, worst for people.",
        # The one style that reads well as a suffix: the checkpoint is
        # already tuned for this, so the words only need to nudge it.
        prompt_template=(
            "{prompt}, shot on 35mm film, natural light, shallow depth of field, "
            "subtle film grain, realistic textures, candid documentary photography"
        ),
        negative_prompt=(
            f"{_BASE_NEGATIVE}, cgi, 3d render, illustration, "
            "overly smooth, plastic, oversaturated"
        ),
        sample="photoreal.jpg",
    ),
    ArtStyle(
        id="anime",
        name="Anime",
        description="Cel shading, clean line art, saturated colour.",
        prompt_template=(
            "anime key visual, cel shaded, clean bold line art, vibrant flat colors, "
            "studio anime production still of {prompt}"
        ),
        negative_prompt=f"{_BASE_NEGATIVE}, {_ANTI_PHOTO}, 3d render",
        sample="anime.jpg",
    ),
    ArtStyle(
        id="toon3d",
        name="3D Toon",
        description="Big-eyed animated-film characters, soft light.",
        prompt_template=(
            "3D animated movie still, stylized cartoon character with large expressive eyes, "
            "smooth rounded shapes, soft global illumination, vibrant saturated colors, "
            "animation studio render of {prompt}"
        ),
        negative_prompt=f"{_BASE_NEGATIVE}, {_ANTI_PHOTO}, flat 2d, line art",
        sample="toon3d.jpg",
    ),
    ArtStyle(
        id="comic",
        name="Comic",
        description="Inked outlines and halftone shading.",
        prompt_template=(
            "comic book panel, bold black ink outlines, halftone dot shading, "
            "limited flat color palette, dramatic angle, graphic novel illustration of {prompt}"
        ),
        negative_prompt=f"{_BASE_NEGATIVE}, {_ANTI_PHOTO}, 3d render, soft gradients",
        sample="comic.jpg",
    ),
    ArtStyle(
        id="clay",
        name="Claymation",
        description="Plasticine models with visible fingerprints.",
        prompt_template=(
            "claymation stop motion still, handmade plasticine clay figure with visible "
            "fingerprints and sculpting tool marks, miniature handcrafted set, "
            "soft studio lighting, clay model of {prompt}"
        ),
        negative_prompt=f"{_BASE_NEGATIVE}, {_ANTI_PHOTO}, cgi, smooth digital render, flat 2d",
        sample="clay.jpg",
    ),
    ArtStyle(
        id="pixel",
        name="Pixel Art",
        description="Chunky 16-bit sprites, limited palette.",
        prompt_template=(
            "pixel art, 16-bit retro video game sprite art, crisp visible pixels, "
            "limited color palette, dithering, isometric game scene of {prompt}"
        ),
        negative_prompt=f"{_BASE_NEGATIVE}, {_ANTI_PHOTO}, smooth gradients, antialiased, 3d render",
        sample="pixel.jpg",
    ),
)

DEFAULT_ART_STYLE = ART_STYLES[0]


def by_id(style_id: str | None) -> ArtStyle:
    """Resolve a style id, falling back to the photoreal default.

    Never raises: an unknown id on a project that has already been charged
    should degrade to the default look rather than fail the render.
    """
    if not style_id:
        return DEFAULT_ART_STYLE
    return next((style for style in ART_STYLES if style.id == style_id), DEFAULT_ART_STYLE)
