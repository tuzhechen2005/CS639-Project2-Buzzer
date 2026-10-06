import { describe, expect, it } from 'vitest';
import { decodeEntities, parsePrompt, promptPlainText } from './promptMarkup';

describe('decodeEntities', () => {
  it('decodes what the backend sanitizer produces', () => {
    expect(decodeEntities('Is x &lt; 5 &amp; y &gt; 2?')).toBe('Is x < 5 & y > 2?');
    expect(decodeEntities('&quot;hi&quot; &#39;there&#39; &#x27;x&#x27;')).toBe(`"hi" 'there' 'x'`);
  });

  it('leaves unknown or invalid entities as written', () => {
    expect(decodeEntities('&bogus; &#0; &')).toBe('&bogus; &#0; &');
  });
});

describe('parsePrompt', () => {
  it('turns the four allowed tags into nodes', () => {
    expect(parsePrompt('Which has the <b>most</b> sides?')).toEqual([
      'Which has the ',
      { tag: 'b', children: ['most'] },
      ' sides?',
    ]);
    expect(parsePrompt('<i>a <u>b</u></i><br>c')).toEqual([
      { tag: 'i', children: ['a ', { tag: 'u', children: ['b'] }] },
      { tag: 'br' },
      'c',
    ]);
  });

  it('accepts upper case and self-closing breaks', () => {
    expect(parsePrompt('<B>x</B><br/>y<BR />z')).toEqual([
      { tag: 'b', children: ['x'] },
      { tag: 'br' },
      'y',
      { tag: 'br' },
      'z',
    ]);
  });

  it('keeps anything else as plain text, including decoded entities', () => {
    expect(parsePrompt('a &lt;script&gt;x&lt;/script&gt; <span>b</span>')).toEqual([
      'a <script>x</script> <span>b</span>',
    ]);
  });

  it('recovers from badly nested or unbalanced tags', () => {
    expect(parsePrompt('<b>open')).toEqual([{ tag: 'b', children: ['open'] }]);
    expect(parsePrompt('stray</i> end')).toEqual(['stray end']);
    expect(parsePrompt('<b><i>x</b>y')).toEqual([
      { tag: 'b', children: [{ tag: 'i', children: ['x'] }] },
      'y',
    ]);
  });

  it('returns plain text unchanged', () => {
    expect(parsePrompt('Plain prompt')).toEqual(['Plain prompt']);
    expect(parsePrompt('')).toEqual([]);
  });
});

describe('promptPlainText', () => {
  it('drops tags and decodes entities', () => {
    expect(promptPlainText('Is <b>x</b> &lt; 5?<br>Yes')).toBe('Is x < 5? Yes');
  });
});
