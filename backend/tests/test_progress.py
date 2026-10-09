"""Progress a page can trust: the latest state for whoever connects late,
and a long transcription that says how far it is and how long is left."""

from __future__ import annotations

import asyncio
import threading
import time

from app.schemas.project import RenderProgress, RenderStage
from app.services.connection_manager import ConnectionManager


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def test_a_page_opened_mid_render_gets_the_latest_progress_at_once():
    manager = ConnectionManager()
    await manager.broadcast(
        RenderProgress(
            project_id="p",
            stage=RenderStage.TRANSCRIPTION,
            progress_pct=18,
            message="Transcribing: 53%",
            phase="transcribing",
            phase_fraction=0.53,
            eta_s=240,
        )
    )
    late = _Socket()
    await manager.connect("p", late)
    assert [m["phase_fraction"] for m in late.sent] == [0.53]
    assert late.sent[0]["eta_s"] == 240


async def test_a_finished_render_is_not_replayed():
    manager = ConnectionManager()
    await manager.broadcast(
        RenderProgress(project_id="p", stage=RenderStage.DONE, progress_pct=100, message="done")
    )
    late = _Socket()
    await manager.connect("p", late)
    assert late.sent == []


async def test_transcription_reports_its_progress_and_the_time_left(monkeypatch):
    from app.services import render_manager

    seen: list[dict] = []

    async def fake_emit(project_id, **kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(render_manager, "_emit", fake_emit)
    report = render_manager._transcription_reporter("p")

    def whisper():
        # A hundred segments, a hundredth of the audio every 10ms: a second
        # to read it all, so a second's worth of estimate at the start.
        for i in range(1, 101):
            report(i / 100)
            time.sleep(0.01)

    worker = threading.Thread(target=whisper)
    worker.start()
    while worker.is_alive():
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)

    fractions = [m["phase_fraction"] for m in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert all(m["phase"] == "transcribing" for m in seen)
    assert all(10 <= m["progress_pct"] <= 25 for m in seen)
    halfway = min(seen, key=lambda m: abs(m["phase_fraction"] - 0.5))
    assert halfway["eta_s"] is not None and halfway["eta_s"] <= 2


def test_whisper_progress_is_the_end_of_the_latest_segment():
    from app.engines import audio_engine

    got: list[float] = []
    audio_engine._report(got.append, 30.0, 120.0)
    audio_engine._report(got.append, 130.0, 120.0)
    audio_engine._report(None, 30.0, 120.0)
    assert got == [0.25, 1.0]
