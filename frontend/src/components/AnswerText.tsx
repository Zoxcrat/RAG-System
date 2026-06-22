import { parseAnswer } from '../citations';

interface Props {
  answer: string;
  onCite: (page: number) => void;
  // Highlighted citation page.
  activePage?: number;
}

// Renders answer text with "[page N]" tokens as page-jump buttons.
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
