import { parseAnswer } from '../citations';

interface Props {
  answer: string;
  onCite: (page: number) => void;
  // The page currently shown in the viewer; its citation(s) get highlighted.
  activePage?: number;
}

// Renders the answer text, turning every "[página N]" token into a button that
// jumps the viewer to page N. Plain text is rendered as-is.
export function AnswerText({ answer, onCite, activePage }: Props) {
  const segments = parseAnswer(answer);

  return (
    <p className="answer-text">
      {segments.map((seg, i) =>
        seg.type === 'text' ? (
          <span key={i}>{seg.value}</span>
        ) : (
          <button
            key={i}
            type="button"
            className={seg.page === activePage ? 'citation citation-active' : 'citation'}
            title={`Go to page ${seg.page}`}
            onClick={() => onCite(seg.page)}
          >
            {seg.label}
          </button>
        ),
      )}
    </p>
  );
}
