import type { Project, ScriptFormat } from "./types";

/** The formats made as series: one premise, episodes that continue. */
export const SERIES_FORMATS = ["story", "outbreak"] as const;
export type SeriesFormat = (typeof SERIES_FORMATS)[number];

export function isSeriesFormat(format: ScriptFormat | string | undefined): format is SeriesFormat {
  return (SERIES_FORMATS as readonly string[]).includes(format ?? "");
}

/** A series: its episodes in order, first to last. */
export interface Series {
  id: string;
  format: SeriesFormat;
  episodes: Project[];
}

/**
 * Every series in a list of projects.
 *
 * There is no series record: an episode names the one it continues
 * (`continues_from`), so a series is the chain from an episode that
 * continues nothing. Built here rather than on the server because the
 * library already loads every project and a chain is a few lookups. A
 * branch — two episodes continuing the same one — follows the newer.
 */
export function groupSeries(projects: Project[]): Series[] {
  const episodes = projects.filter((p) => isSeriesFormat(p.config.script_format));
  const next = new Map<string, Project>();
  for (const p of episodes) {
    const parent = p.config.continues_from;
    if (!parent) continue;
    const seen = next.get(parent);
    if (!seen || (p.config.created_at ?? "") > (seen.config.created_at ?? "")) next.set(parent, p);
  }
  const ids = new Set(episodes.map((p) => p.config.id));
  const roots = episodes.filter((p) => !p.config.continues_from || !ids.has(p.config.continues_from));
  return roots
    .map((root) => {
      const chain = [root];
      let at: Project | undefined = root;
      while (at && (at = next.get(at.config.id)) && chain.length < 99) chain.push(at);
      return { id: root.config.id, format: root.config.script_format as SeriesFormat, episodes: chain };
    })
    .sort((a, b) =>
      (b.episodes.at(-1)?.config.created_at ?? "").localeCompare(a.episodes.at(-1)?.config.created_at ?? "")
    );
}

/** The series an episode belongs to, by any of its episodes' ids. */
export function seriesOf(all: Series[], projectId: string): Series | undefined {
  return all.find((s) => s.episodes.some((e) => e.config.id === projectId));
}

/** What a format's episode is, for the form's summary. */
export const EPISODE_SHAPE: Record<SeriesFormat, Record<"short" | "medium", { seconds: string; shots: string }>> = {
  story: { short: { seconds: "~60", shots: "18-24" }, medium: { seconds: "~120", shots: "38-48" } },
  outbreak: { short: { seconds: "~45", shots: "7-8" }, medium: { seconds: "~75", shots: "11-13" } },
};
