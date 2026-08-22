"""What this machine can actually get through, measured rather than guessed.

Twelve renders have ever run here, never more than one at a time, so every
capacity number so far is an extrapolation from an idle system. That is
not enough to decide whether to pay for a bigger machine, and it is not
enough to know what a busy launch day does to the queue.

    python scripts/loadtest.py --count 4                     # stock, free
    python scripts/loadtest.py --count 4 --mode fast_hybrid   # costs money

Reports throughput and, more usefully, **seconds per scene** — scene count
varies between renders even at the same length setting, so the raw total
cannot be compared across runs and the per-scene figure can.

Safe to run against the live service, with two deliberate constraints:

  * It refuses to start while a real render is in flight. A load test that
    makes a paying customer wait has measured the wrong thing.
  * It deletes every project it created. `scripts/funnel.py` counts all
    rows in `projects`, not just the ones with a user, so leaving these
    behind would quietly corrupt the numbers the launch decision rests on.

Nothing here touches the credit ledger: projects are created through the
store directly, so no charge path is involved.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings, project_dir  # noqa: E402
from app.schemas.project import (  # noqa: E402
    LLMConfig,
    LLMProvider,
    ProjectConfig,
    ProjectStatus,
    VideoLength,
    VisualMode,
)
from app.services import db, project_store  # noqa: E402
from app.services.render_manager import RenderTaskQueue  # noqa: E402

# Marked so a run killed halfway leaves something greppable behind.
TOPIC = "loadtest-do-not-keep"

# The same words every time, so two runs differ by what is being tested
# rather than by what the LLM felt like writing.
RAW_SCRIPT = (
    "Bees find flowers by seeing ultraviolet patterns we cannot. "
    "The petals carry landing marks, invisible to us, obvious to them. "
    "A meadow to a bee is a runway map. "
    "What looks plain to you is signposted for something else."
)


async def _in_flight() -> list[str]:
    """Renders belonging to somebody, running right now."""
    pool = db.optional_pool()
    if pool is None:
        return []
    rows = await pool.fetch(
        "select id from projects where status = 'rendering' and user_id is not null"
    )
    return [str(r["id"]) for r in rows]


class Timed:
    """One render's life: queued, started, finished."""

    def __init__(self) -> None:
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.status = "pending"
        self.scenes = 0

    @property
    def queued_s(self) -> float:
        return (self.started_at or 0.0)

    @property
    def render_s(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


async def _wait_for(ids: list[str], timeout_s: float) -> dict[str, Timed]:
    """Poll until every project reaches a terminal state.

    Queue wait and render time are recorded separately, which matters more
    than it sounds: measured from submit, the last pair in a batch of six
    looked three times slower than the first pair when it was simply
    behind them in the queue. Reading that as "renders get slower under
    load" would have argued for hardware the numbers do not support.
    """
    t0 = time.monotonic()
    timed = {i: Timed() for i in ids}
    while any(t.status == "pending" for t in timed.values()):
        if time.monotonic() - t0 > timeout_s:
            break
        for project_id, t in timed.items():
            if t.status != "pending":
                continue
            project = await project_store.get_project(project_id)
            if project is None:
                continue
            now = time.monotonic() - t0
            if t.started_at is None and project.status != ProjectStatus.DRAFT:
                t.started_at = now
            if project.status in (ProjectStatus.COMPLETE, ProjectStatus.FAILED):
                # A render that finished between two polls never looked
                # like it started; treat the poll before as its start.
                if t.started_at is None:
                    t.started_at = max(0.0, now - 2)
                t.finished_at = now
                t.status = str(project.status)
                t.scenes = len(project.script.scenes) if project.script else 0
        await asyncio.sleep(2)
    return timed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--mode", default="stock_media",
                        choices=[m.value for m in VisualMode])
    parser.add_argument("--length", default="medium",
                        choices=[length.value for length in VideoLength])
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--keep", action="store_true",
                        help="leave the projects behind for inspection")
    args = parser.parse_args()

    settings = get_settings()
    if settings.database_url:
        pool = await db.connect(settings.database_url)
        project_store.configure(pool)

    busy = await _in_flight()
    if busy:
        print(f"Refusing to start: {len(busy)} real render(s) in flight.")
        print("A load test that makes a customer wait has measured the wrong thing.")
        return 1

    queue = RenderTaskQueue(settings)
    queue.start()

    print(f"\n{args.count} x {args.mode} / {args.length}")
    print(f"concurrency: {settings.max_concurrent_renders} renders, "
          f"load average before: {os.getloadavg()[0]:.2f}\n")

    created: list[str] = []
    t0 = time.monotonic()
    for _ in range(args.count):
        project = await project_store.create_project(
            ProjectConfig(
                topic=TOPIC,
                raw_script=RAW_SCRIPT,
                visual_mode=VisualMode(args.mode),
                video_length=VideoLength(args.length),
                # Built from settings exactly as create_project does it
                # (api/routes/projects.py). LLMConfig's own defaults point
                # at a local Ollama, which does not exist on a hosted box —
                # the first run of this script failed all six renders on a
                # connection error before reaching anything worth timing.
                llm=LLMConfig(
                    provider=LLMProvider(settings.llm_provider),
                    model=settings.llm_model,
                    base_url=settings.ollama_base_url,
                    api_key=settings.openai_api_key,
                ),
            )
        )
        created.append(project.config.id)
        await queue.submit(project)

    results = await _wait_for(created, args.timeout)
    wall = time.monotonic() - t0
    await queue.stop()

    ok = {k: v for k, v in results.items() if v.status == "complete"}
    failed = [k for k, v in results.items() if v.status == "failed"]
    unfinished = [k for k, v in results.items() if v.status == "pending"]

    print(f"per render{'':14}queued   render  scenes   per scene\n")
    for project_id, t in sorted(results.items(), key=lambda kv: kv[1].queued_s):
        render_s = t.render_s
        per_scene = f"{render_s / t.scenes:5.1f}s" if render_s and t.scenes else "    —"
        print(f"  {project_id[:8]}  {t.status:<9}"
              f"{t.queued_s:7.0f}s {render_s or 0:7.0f}s {t.scenes:>6}   {per_scene}")

    print()
    if ok:
        renders = [v.render_s for v in ok.values() if v.render_s]
        per_scene = [v.render_s / v.scenes for v in ok.values() if v.render_s and v.scenes]
        print(f"  finished          {len(ok)}/{args.count}")
        print(f"  wall clock        {wall:.0f}s for the whole batch")
        print(f"  throughput        {len(ok) / wall * 3600:.1f} renders/hour"
              "   <- the number that decides capacity")
        print(f"  median render     {statistics.median(renders):.0f}s (excluding queue wait)")
        if per_scene:
            print(f"  median per scene  {statistics.median(per_scene):.1f}s")
    if failed:
        print(f"  FAILED            {len(failed)} — check the API logs")
    if unfinished:
        print(f"  never finished    {len(unfinished)} (timed out)")
    print(f"  load average      {os.getloadavg()[0]:.2f} after\n")

    if args.keep:
        print("Left behind on request. These rows are counted by funnel.py — "
              f"delete them with: topic = {TOPIC!r}")
    else:
        for project_id in created:
            await project_store.delete_project(project_id)
            shutil.rmtree(project_dir(project_id), ignore_errors=True)
        print(f"Cleaned up {len(created)} projects and their files.")

    if settings.database_url:
        await db.disconnect()
    return 0 if ok and not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
