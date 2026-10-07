import { Fragment, type ReactNode } from 'react';
import { parsePrompt, type PromptNode } from '../lib/promptMarkup';

function render(nodes: PromptNode[]): ReactNode[] {
  return nodes.map((n, i) => {
    if (typeof n === 'string') return <Fragment key={i}>{n}</Fragment>;
    if (n.tag === 'br') return <br key={i} />;
    const Tag = n.tag;
    return <Tag key={i}>{render(n.children)}</Tag>;
  });
}

/**
 * A question prompt with its formatting: <b>, <i>, <u> and <br> are shown as formatting and
 * entities such as &lt; as the characters they stand for (lib/promptMarkup.ts). Everything is
 * rendered as React elements and text, never as raw HTML.
 */
export function PromptText({ prompt }: { prompt: string }) {
  return <>{render(parsePrompt(prompt))}</>;
}
