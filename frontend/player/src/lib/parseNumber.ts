// Parses what a player typed into a number for a numeric_estimate question.
// Exactly one of three patterns must match (ASCII digits only), otherwise null:
//   A  plain         1665  1665.5  .5  5.  -12  -.5  -0  007
//   B  thousands     1,665  1,665,000  1,665.5   (groups of exactly three digits)
//   C  comma decimal 1,5  1,66  0,5               (one or two digits after the comma)
// The result must be finite and at most 1e15 in magnitude (the server's limit).

const PLAIN = /^-?(\d+\.?\d*|\.\d+)$/;
const THOUSANDS = /^-?\d{1,3}(,\d{3})+(\.\d+)?$/;
const COMMA_DECIMAL = /^-?\d+,\d{1,2}$/;

export const MAX_MAGNITUDE = 1e15;

export function parseNumber(text: string): number | null {
  const t = text.trim();
  let normalised: string;
  if (PLAIN.test(t)) normalised = t;
  else if (THOUSANDS.test(t)) normalised = t.replace(/,/g, '');
  else if (COMMA_DECIMAL.test(t)) normalised = t.replace(',', '.');
  else return null;

  const n = Number(normalised);
  if (!Number.isFinite(n) || Math.abs(n) > MAX_MAGNITUDE) return null;
  return n === 0 ? 0 : n; // never -0
}
