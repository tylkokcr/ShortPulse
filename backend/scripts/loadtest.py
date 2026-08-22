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


async def _wait_for(ids: list[str], timeout_s: float) -> dict[str, tuple[str, float, int]]:
    """Poll until every project reaches a terminal state.

    Returns id -> (status, seconds since submit, scene count).
    """
    started = time.monotonic()
    done: dict[str, tuple[str, float, int]] = {}
    while len(done) < len(ids):
        if time.monotonic() - started > timeout_s:
            break
        for project_id in ids:
            if project_id in done:
                continue
            project = await project_store.get_project(project_id)
            if project is None:
                continue
            if project.status in (ProjectStatus.COMPLETE, ProjectStatus.FAILED):
                scenes = len(project.script.scenes) if project.script else 0
                done[project_id] = (
                    str(project.status),
                    time.monotonic() - started,
                    scenes,
                )
        await asyncio.sleep(2)
    return done


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
            )
        )
        created.append(project.config.id)
        await queue.submit(project)

    results = await _wait_for(created, args.timeout)
    wall = time.monotonic() - t0
    await queue.stop()

    ok = {k: v for k, v in results.items() if v[0] == "complete"}
    failed = [k for k, v in results.items() if v[0] == "failed"]
    unfinished = [i for i in created if i not in results]

    print("per render\n")
    for project_id, (status, seconds, scenes) in sorted(results.items(), key=lambda kv: kv[1][1]):
        per_scene = f"{seconds / scenes:5.1f}s/scene" if scenes else "  — "
        print(f"  {project_id[:8]}  {status:<9} {seconds:6.1f}s  {scenes:>2} scenes  {per_scene}")

    print()
    if ok:
        totals = [v[1] for v in ok.values()]
        per_scene = [v[1] / v[2] for v in ok.values() if v[2]]
        print(f"  finished          {len(ok)}/{args.count}")
        print(f"  wall clock        {wall:.0f}s for the whole batch")
        print(f"  throughput        {len(ok) / wall * 3600:.1f} renders/hour")
        print(f"  median render     {statistics.median(totals):.0f}s")
        if per_scene:
            print(f"  median per scene  {statistics.median(per_scene):.1f}s"
                  "   <- compare this across runs")
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
