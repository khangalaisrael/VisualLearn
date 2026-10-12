/**
 * "Find more online": for the series and each of its subtopics, a link that
 * opens a YouTube search and one that opens a web search. The links are built
 * from the topic names, so they cost nothing and can never point at a page
 * that does not exist; what they find is the search engine's choice, not ours.
 */

const MAX_TOPICS = 12;

/** Where a search for `topic` (within the series' subject) opens. */
export function searchLinks(topic: string, seriesTitle: string): { youtube: string; web: string } {
  const clean = topic.trim();
  // "Beta Reduction" alone is ambiguous; "Beta Reduction Lambda Calculus" is not.
  const words = clean.toLowerCase().includes(seriesTitle.trim().toLowerCase()) ? clean : `${clean} ${seriesTitle.trim()}`;
  const query = encodeURIComponent(words.trim());
  return {
    youtube: `https://www.youtube.com/results?search_query=${query}`,
    web: `https://www.google.com/search?q=${query}`,
  };
}

/** The series title, then its subtopics without repeats, in the order given. */
export function topicsOf(seriesTitle: string, subtopics: (string | null)[]): string[] {
  const seen = new Set<string>([seriesTitle.trim().toLowerCase()]);
  const topics = [seriesTitle.trim()];
  for (const subtopic of subtopics) {
    const name = subtopic?.trim();
    if (!name || seen.has(name.toLowerCase())) continue;
    seen.add(name.toLowerCase());
    topics.push(name);
    if (topics.length > MAX_TOPICS) break;
  }
  return topics;
}

const LINK =
  "rounded-sm px-2 py-1 text-xs font-medium text-indigo-600 transition-colors duration-[120ms] hover:bg-indigo-50 dark:text-indigo-300";

export function SeriesLinks({ seriesTitle, subtopics }: { seriesTitle: string; subtopics: (string | null)[] }): JSX.Element {
  const topics = topicsOf(seriesTitle, subtopics);
  return (
    <section className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 shadow-subtle" aria-labelledby="find-more-online">
      <div className="flex flex-col gap-0.5">
        <h3 id="find-more-online" className="text-sm font-semibold text-slate-800">
          Find more online
        </h3>
        <p className="text-xs leading-relaxed text-slate-500">
          Each link opens a search for that topic in a new tab. The results are the search engine's, not checked by us.
        </p>
      </div>
      <ul className="flex flex-col divide-y divide-slate-100">
        {topics.map((topic) => {
          const links = searchLinks(topic, seriesTitle);
          return (
            <li key={topic} className="flex items-center gap-2 py-1">
              <span className="min-w-0 flex-1 truncate text-sm text-slate-700">{topic}</span>
              <a href={links.youtube} target="_blank" rel="noreferrer" className={LINK} aria-label={`Search YouTube for ${topic}`}>
                YouTube
              </a>
              <a href={links.web} target="_blank" rel="noreferrer" className={LINK} aria-label={`Search the web for ${topic}`}>
                Web
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
