/**
 * A project card that has not arrived yet.
 *
 * Deliberately the same geometry as `ProjectCard`: the 9:16 poster, the
 * title line, the meta line beneath it, at the same gaps. That is what
 * makes it useful rather than decorative — the grid is already its final
 * shape when the request returns, so the real cards replace these in
 * place instead of pushing a page into existence.
 *
 * Not a shared `<Skeleton>` primitive. There is one list in this app and
 * one card shape in it; a generic box with width and height props would
 * be the same number of lines and would stop matching the card the first
 * time the card changed.
 */
export function ProjectCardSkeleton() {
  return (
    <div className="flex flex-col gap-2.5" aria-hidden>
      <div className="skeleton-sweep aspect-[9/16] rounded-md border border-border bg-surface" />
      <div className="flex flex-col gap-1.5">
        {/* Widths that vary a little, because eleven identical bars read
            as a loading graphic and a page of real titles does not. */}
        <div className="skeleton-sweep h-3 w-4/5 rounded bg-surface" />
        <div className="skeleton-sweep h-2 w-1/2 rounded bg-surface" />
      </div>
    </div>
  );
}
