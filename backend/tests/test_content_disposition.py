"""The video's Content-Disposition header, for titles latin-1 cannot hold."""

import unicodedata
from urllib.parse import unquote

import pytest
from starlette.responses import Response

from app.api.routes.projects import content_disposition


@pytest.mark.parametrize(
    "title",
    [
        "Kuşlar neden göç eder?",
        "ışık",
        # What macOS hands over for a file called "kürk": u + U+0308.
        unicodedata.normalize("NFD", "10.06.2026_kürk.mp4"),
        'a "quoted" \\ name',
        "",
    ],
)
def test_any_title_makes_a_header_that_can_be_sent(title: str) -> None:
    header = content_disposition("inline", title, fallback="abc123")
    # This is what raised before: Starlette encodes header values as latin-1.
    Response(b"", headers={"Content-Disposition": header})
    assert header.isascii()


def test_the_real_name_survives_in_filename_star_and_the_extension_is_not_doubled() -> None:
    header = content_disposition(
        "inline", unicodedata.normalize("NFD", "10.06.2026_kürk.mp4"), fallback="x"
    )
    encoded = header.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == "10.06.2026_kürk.mp4"
    assert 'filename="10.06.2026_kurk.mp4"' in header


def test_turkish_i_reads_as_i_in_the_ascii_fallback() -> None:
    assert 'filename="isik.mp4"' in content_disposition("inline", "ışık", fallback="x")


def test_an_empty_title_falls_back_to_the_project_id() -> None:
    assert 'filename="abc123.mp4"' in content_disposition("attachment", "  ", fallback="abc123")
