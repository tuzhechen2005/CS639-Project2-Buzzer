// Question prompts may carry four formatting tags: <b>, <i>, <u> and <br>. The backend keeps only
// those (backend/app/services/game_admin_service.py, sanitize_prompt) and stores every other "<",
// ">" and "&" as an HTML entity (&lt; &gt; &amp;). This parses such a prompt into a small tree so
// the apps can show the formatting without ever inserting raw HTML: anything that is not one of
// the four tags stays plain text, and the entities are decoded.
//
// Byte-identical in frontend/player/src/lib and frontend/host/src/lib (the apps share no code;
// tests/unit/test_prompt_markup_copies.py checks they match). Imports nothing.

export type PromptTag = 'b' | 'i' | 'u';

export type PromptNode = string | { tag: PromptTag; children: PromptNode[] } | { tag: 'br' };

const TAG = /<(\/?)(b|i|u|br)\s*\/?>/gi;

const NAMED: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

/** Decode the HTML entities the backend's sanitizer produces; unknown ones stay as written. */
export function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (whole, body: string) => {
    if (body[0] === '#') {
      const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : whole;
    }
    return NAMED[body.toLowerCase()] ?? whole;
  });
}

/**
 * Parse a prompt into text and b/i/u/br nodes. Well-formed input (what the sanitizer stores) maps
 * one to one; for anything else: a closing tag closes the nearest matching open tag (and any
 * opened inside it), a closing tag with no match is dropped, and tags left open at the end close.
 */
export function parsePrompt(prompt: string): PromptNode[] {
  const root: PromptNode[] = [];
  const stack: { tag: PromptTag; children: PromptNode[] }[] = [];
  const current = () => (stack.length ? stack[stack.length - 1].children : root);
  const pushText = (raw: string) => {
    if (!raw) return;
    const text = decodeEntities(raw);
    const list = current();
    const last = list[list.length - 1];
    if (typeof last === 'string') list[list.length - 1] = last + text;
    else list.push(text);
  };

  let at = 0;
  for (const m of prompt.matchAll(TAG)) {
    pushText(prompt.slice(at, m.index));
    at = (m.index ?? 0) + m[0].length;
    const closing = m[1] === '/';
    const name = m[2].toLowerCase() as PromptTag | 'br';
    if (name === 'br') {
      current().push({ tag: 'br' });
    } else if (!closing) {
      const node = { tag: name, children: [] as PromptNode[] };
      current().push(node);
      stack.push(node);
    } else {
      const open = stack.map((n) => n.tag).lastIndexOf(name);
      if (open >= 0) stack.length = open;
    }
  }
  pushText(prompt.slice(at));
  return root;
}

/** The prompt as plain text (tags dropped, line breaks as spaces): for titles and labels. */
export function promptPlainText(prompt: string): string {
  const flat = (nodes: PromptNode[]): string =>
    nodes.map((n) => (typeof n === 'string' ? n : n.tag === 'br' ? ' ' : flat(n.children))).join('');
  return flat(parsePrompt(prompt));
}
