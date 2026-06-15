// Parses the LLM answer into text + citation segments. Citations look like
// "[página 42]" (the exact format the backend prompt requests); each becomes a
// clickable button in the UI that jumps the PDF viewer to that page.
export type AnswerSegment =
  | { type: 'text'; value: string }
  | { type: 'citation'; page: number; label: string };

const CITATION_RE = /\[página\s+(\d+)\]/g;

export function parseAnswer(answer: string): AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let lastIndex = 0;

  for (const match of answer.matchAll(CITATION_RE)) {
    const start = match.index ?? 0;
    if (start > lastIndex) {
      segments.push({ type: 'text', value: answer.slice(lastIndex, start) });
    }
    segments.push({ type: 'citation', page: Number(match[1]), label: match[0] });
    lastIndex = start + match[0].length;
  }

  if (lastIndex < answer.length) {
    segments.push({ type: 'text', value: answer.slice(lastIndex) });
  }

  return segments;
}
