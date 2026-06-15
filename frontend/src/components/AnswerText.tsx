import { parseAnswer } from '../citations';

interface Props {
  answer: string;
  onCite: (page: number) => void;
}

// Renders the answer text, turning every "[página N]" token into a button that
// jumps the viewer to page N. Plain text is rendered as-is.
export function AnswerText({ answer, onCite }: Props) {
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
            className="citation"
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
