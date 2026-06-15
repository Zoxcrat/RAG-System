import { describe, it, expect } from 'vitest';
import { parseAnswer } from './citations';

describe('parseAnswer', () => {
  it('returns a single text segment when there are no citations', () => {
    expect(parseAnswer('plain answer')).toEqual([
      { type: 'text', value: 'plain answer' },
    ]);
  });

  it('splits a citation out of the surrounding text', () => {
    expect(parseAnswer('Use the bolt [página 42] now')).toEqual([
      { type: 'text', value: 'Use the bolt ' },
      { type: 'citation', page: 42, label: '[página 42]' },
      { type: 'text', value: ' now' },
    ]);
  });

  it('handles a citation at the very start (no empty leading text)', () => {
    expect(parseAnswer('[página 7] is the page')).toEqual([
      { type: 'citation', page: 7, label: '[página 7]' },
      { type: 'text', value: ' is the page' },
    ]);
  });

  it('parses multiple citations', () => {
    const cites = parseAnswer('see [página 3] and [página 10]').filter(
      (s) => s.type === 'citation',
    );
    expect(cites).toEqual([
      { type: 'citation', page: 3, label: '[página 3]' },
      { type: 'citation', page: 10, label: '[página 10]' },
    ]);
  });

  it('tolerates extra whitespace inside the token', () => {
    const cites = parseAnswer('x [página   5] y').filter((s) => s.type === 'citation');
    expect(cites).toEqual([{ type: 'citation', page: 5, label: '[página   5]' }]);
  });

  it('handles an empty answer', () => {
    expect(parseAnswer('')).toEqual([]);
  });
});
