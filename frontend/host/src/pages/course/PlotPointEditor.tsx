// The plot_point part of the question editor (docs/plans/t7-plot-the-point.md, P8): form state,
// the client-side mirror of the server's rules (plotProblems; the server stays the authority),
// the payload, and the form fields with a live preview that sets the target when clicked.
// QuestionEditorPage.tsx holds the shared parts (type, grading, prompt, time, Save).

import { useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { PlotScatter } from '../../components/PlotScatter';
import {
  formatCoord,
  formatGridPoint,
  graphToGrid,
  gridSize,
  gridToGraph,
  type GraphPoint,
  type PlotConfig,
  type PlotOverlay,
} from '../../lib/plotGeometry';

export const PP_DEFAULT_TIME = 45;
const PP_MAX_BANDS = 5;
const PP_MAX_OVERLAYS = 20;
const PP_LIMIT = 1e6;
const PP_LABEL_MAX = 20;
const PP_TOL = 1e-9;

/** The steps the server accepts: 1, 2 or 5 times a power of ten, 0.001 … 500000. */
export const PP_STEPS: number[] = [];
for (let k = -3; k <= 5; k++) {
  for (const m of [1, 2, 5]) PP_STEPS.push(Number((m * 10 ** k).toPrecision(1)));
}

// Server messages (P1), so the editor and a 422 say the same thing.
export const PP_MSG = {
  limits: 'plot_point axis limits must be finite numbers with min < max',
  multiples: 'plot_point axis limits must be multiples of their step',
  cells: 'plot_point allows 1 to 20 cells per axis',
  labels: 'plot_point labels must be 1 to 20 characters',
  overlay: 'plot_point overlay is invalid',
  target: 'plot_point target must be a grid point inside the plane',
  bandCount: 'bands must be a list of 1 to 5 items',
  band: 'each band needs whole-cell within ≥ 0 and points > 0',
  within: 'band within values must strictly increase',
  points: 'band points must strictly decrease',
};

export type PpOverlayKind = 'point' | 'line' | 'polynomial';

/** An overlay as typed: every number is kept as text so a half-typed value is not forced to 0. */
export interface PpOverlay {
  kind: PpOverlayKind;
  x: string;
  y: string;
  x1: string;
  y1: string;
  x2: string;
  y2: string;
  /** c0 … c3 of y = c0 + c1·x + c2·x² + c3·x³; a blank is 0, trailing blanks are dropped. */
  coefficients: [string, string, string, string];
  label: string;
}

export interface PpBand { within: string; points: string }

export interface PpForm {
  ppXMin: string;
  ppXMax: string;
  ppXStep: number;
  ppYMin: string;
  ppYMax: string;
  ppYStep: number;
  ppXLabel: string;
  ppYLabel: string;
  ppOverlays: PpOverlay[];
  /** Graph units, stored as roundToStep's number. Kept (and flagged) when the axes change. */
  ppTarget: GraphPoint | null;
  ppBands: PpBand[];
}

export const ppDefaultBands = (): PpBand[] => [
  { within: '0', points: '100' },
  { within: '1', points: '50' },
];

export const ppDefaultForm = (): PpForm => ({
  ppXMin: '-10',
  ppXMax: '10',
  ppXStep: 1,
  ppYMin: '-10',
  ppYMax: '10',
  ppYStep: 1,
  ppXLabel: '',
  ppYLabel: '',
  ppOverlays: [],
  ppTarget: null,
  ppBands: ppDefaultBands(),
});

const emptyOverlay = (kind: PpOverlayKind): PpOverlay => ({
  kind, x: '', y: '', x1: '', y1: '', x2: '', y2: '', coefficients: ['', '', '', ''], label: '',
});

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/** A typed number, or null if blank, not finite, or larger than the server allows. */
function num(text: string): number | null {
  if (text.trim() === '') return null;
  const v = Number(text);
  return Number.isFinite(v) && Math.abs(v) <= PP_LIMIT ? v : null;
}

const isWhole = (v: number) => Math.abs(v - Math.round(v)) <= PP_TOL;

/** The plane, if the axes pass the server's rules 1–4; otherwise the first failing message. */
export function ppPlane(f: PpForm): { config: PlotConfig } | { problem: string } {
  const [xMin, xMax, yMin, yMax] = [f.ppXMin, f.ppXMax, f.ppYMin, f.ppYMax].map(num);
  if (xMin === null || xMax === null || yMin === null || yMax === null || xMin >= xMax || yMin >= yMax) {
    return { problem: PP_MSG.limits };
  }
  const multiples = (v: number, step: number) => isWhole(v / step);
  if (![xMin, xMax].every((v) => multiples(v, f.ppXStep)) || ![yMin, yMax].every((v) => multiples(v, f.ppYStep))) {
    return { problem: PP_MSG.multiples };
  }
  const config: PlotConfig = { xMin, xMax, xStep: f.ppXStep, yMin, yMax, yStep: f.ppYStep };
  const { nCols, nRows } = gridSize(config);
  if (nCols < 1 || nCols > 20 || nRows < 1 || nRows > 20) return { problem: PP_MSG.cells };
  return { config };
}

/** One overlay as the server wants it, or null if it breaks rule 6. */
function ppOverlayOut(o: PpOverlay): PlotOverlay | null {
  const label = o.label.trim();
  if (label.length > PP_LABEL_MAX) return null;
  const withLabel = (v: PlotOverlay): PlotOverlay => (label ? { ...v, label } : v);
  if (o.kind === 'point') {
    const [x, y] = [num(o.x), num(o.y)];
    return x === null || y === null ? null : withLabel({ kind: 'point', x, y });
  }
  if (o.kind === 'line') {
    const [x1, y1, x2, y2] = [num(o.x1), num(o.y1), num(o.x2), num(o.y2)];
    if (x1 === null || y1 === null || x2 === null || y2 === null) return null;
    if (x1 === x2 && y1 === y2) return null;
    return withLabel({ kind: 'line', x1, y1, x2, y2 });
  }
  const last = o.coefficients.reduce((acc, c, i) => (c.trim() !== '' ? i : acc), -1);
  if (last < 0) return null;
  const coefficients: number[] = [];
  for (const c of o.coefficients.slice(0, last + 1)) {
    const v = c.trim() === '' ? 0 : num(c);
    if (v === null) return null;
    coefficients.push(v);
  }
  return withLabel({ kind: 'polynomial', coefficients });
}

function ppBandsOut(f: PpForm): { within: number; points: number }[] {
  return f.ppBands.map((b) => ({ within: Number(b.within), points: Number(b.points) }));
}

/** Whether a stored target is a grid point inside this plane (the server's rule 8). */
export function ppTargetOk(c: PlotConfig, t: GraphPoint | null): boolean {
  if (!t) return false;
  const { nCols, nRows } = gridSize(c);
  const kx = (t.x - c.xMin) / c.xStep;
  const ky = (t.y - c.yMin) / c.yStep;
  return isWhole(kx) && isWhole(ky) && Math.round(kx) >= 0 && Math.round(kx) <= nCols
    && Math.round(ky) >= 0 && Math.round(ky) <= nRows;
}

/**
 * The server's rules (P1) in order, as its messages. Empty when the form can be saved. The
 * server stays the authority: a drift here shows up as its 422 message, never as bad data.
 */
export function plotProblems(f: PpForm, accuracy: boolean): string[] {
  const problems: string[] = [];
  const plane = ppPlane(f);
  if ('problem' in plane) problems.push(plane.problem);
  if ([f.ppXLabel, f.ppYLabel].some((l) => l.trim().length > PP_LABEL_MAX)) problems.push(PP_MSG.labels);
  if (f.ppOverlays.length > PP_MAX_OVERLAYS) {
    problems.push(`${PP_MSG.overlay} (at most ${PP_MAX_OVERLAYS})`);
  } else {
    f.ppOverlays.forEach((o, i) => {
      if (!ppOverlayOut(o)) problems.push(`${PP_MSG.overlay} (overlay ${i + 1})`);
    });
  }
  if (!accuracy) return problems;
  if (!('config' in plane) || !ppTargetOk(plane.config, f.ppTarget)) problems.push(PP_MSG.target);
  const bands = ppBandsOut(f);
  const maxWithin = 'config' in plane ? Math.max(...Object.values(gridSize(plane.config))) : Infinity;
  if (bands.length < 1 || bands.length > PP_MAX_BANDS) {
    problems.push(PP_MSG.bandCount);
  } else if (bands.some((b, i) => f.ppBands[i].within.trim() === '' || f.ppBands[i].points.trim() === ''
      || !Number.isInteger(b.within) || b.within < 0 || b.within > maxWithin
      || !(b.points > 0) || b.points > PP_LIMIT)) {
    problems.push(PP_MSG.band);
  } else if (bands.some((b, i) => i > 0 && b.within <= bands[i - 1].within)) {
    problems.push(PP_MSG.within);
  } else if (bands.some((b, i) => i > 0 && b.points >= bands[i - 1].points)) {
    problems.push(PP_MSG.points);
  }
  return problems;
}

// ---------------------------------------------------------------------------
// Payload and loading
// ---------------------------------------------------------------------------

/** config and answer_data for the API. Blank labels are omitted; COMPLETENESS sends {}. */
export function buildPpPayload(f: PpForm, accuracy: boolean) {
  const config: Record<string, unknown> = {
    xMin: Number(f.ppXMin), xMax: Number(f.ppXMax), xStep: f.ppXStep,
    yMin: Number(f.ppYMin), yMax: Number(f.ppYMax), yStep: f.ppYStep,
  };
  if (f.ppXLabel.trim()) config.xLabel = f.ppXLabel.trim();
  if (f.ppYLabel.trim()) config.yLabel = f.ppYLabel.trim();
  if (f.ppOverlays.length > 0) config.overlays = f.ppOverlays.map((o) => ppOverlayOut(o) ?? { kind: o.kind });
  if (!accuracy) return { config, answer_data: {} };
  return { config, answer_data: { target: f.ppTarget, bands: ppBandsOut(f) } };
}

/** Points for an ACCURACY question: the first (best) band's. */
export function ppPointsValue(f: PpForm): number {
  return Number(f.ppBands[0]?.points ?? 0);
}

const text = (v: unknown) => (typeof v === 'number' ? String(v) : '');

/** The form fields from a saved question. */
export function ppFromQuestion(config: Record<string, unknown>, answer: Record<string, unknown>): PpForm {
  const f = ppDefaultForm();
  f.ppXMin = text(config.xMin);
  f.ppXMax = text(config.xMax);
  f.ppYMin = text(config.yMin);
  f.ppYMax = text(config.yMax);
  if (typeof config.xStep === 'number') f.ppXStep = config.xStep;
  if (typeof config.yStep === 'number') f.ppYStep = config.yStep;
  f.ppXLabel = typeof config.xLabel === 'string' ? config.xLabel : '';
  f.ppYLabel = typeof config.yLabel === 'string' ? config.yLabel : '';
  const overlays = Array.isArray(config.overlays) ? (config.overlays as Record<string, unknown>[]) : [];
  f.ppOverlays = overlays.map((o) => {
    const kind: PpOverlayKind = o.kind === 'line' || o.kind === 'polynomial' ? o.kind : 'point';
    const coeffs = Array.isArray(o.coefficients) ? (o.coefficients as unknown[]) : [];
    return {
      ...emptyOverlay(kind),
      x: text(o.x), y: text(o.y), x1: text(o.x1), y1: text(o.y1), x2: text(o.x2), y2: text(o.y2),
      coefficients: [0, 1, 2, 3].map((i) => text(coeffs[i])) as PpOverlay['coefficients'],
      label: typeof o.label === 'string' ? o.label : '',
    };
  });
  const t = answer.target as { x?: unknown; y?: unknown } | undefined;
  f.ppTarget = t && typeof t.x === 'number' && typeof t.y === 'number' ? { x: t.x, y: t.y } : null;
  const bands = Array.isArray(answer.bands) ? (answer.bands as { within: number; points: number }[]) : [];
  if (bands.length) f.ppBands = bands.map((b) => ({ within: String(b.within), points: String(b.points) }));
  return f;
}

/** The question list's one line: "Target (3, −2) · 20×20 grid", or "20×20 grid". */
export function ppListSummary(config: Record<string, unknown>, answer: Record<string, unknown>, accuracy: boolean): string {
  const plane = ppPlane(ppFromQuestion(config, answer));
  if (!('config' in plane)) return '';
  const { nCols, nRows } = gridSize(plane.config);
  const grid = `${nCols}×${nRows} grid`;
  const t = answer.target as GraphPoint | undefined;
  if (!accuracy || !t || typeof t.x !== 'number' || typeof t.y !== 'number') return grid;
  return `Target (${formatCoord(t.x, plane.config.xStep)}, ${formatCoord(t.y, plane.config.yStep)}) · ${grid}`;
}

// ---------------------------------------------------------------------------
// Form fields
// ---------------------------------------------------------------------------

const SELECT = 'rounded-xl border border-line-strong bg-surface-raised px-2 py-2 text-fg text-sm focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page';

export function PlotPointFields({
  form,
  accuracy,
  imageId,
  onChange,
}: {
  form: PpForm;
  accuracy: boolean;
  imageId: string | null;
  onChange: (patch: Partial<PpForm>) => void;
}) {
  const plane = ppPlane(form);
  const planeConfig = 'config' in plane ? plane.config : null;
  // The preview draws overlays that are valid now; a half-typed one is skipped until it is.
  const overlaysKey = JSON.stringify(form.ppOverlays);
  const preview: PlotConfig | null = useMemo(() => {
    if (!planeConfig) return null;
    const xLabel = form.ppXLabel.trim() || null;
    const yLabel = form.ppYLabel.trim() || null;
    const overlays = form.ppOverlays.map(ppOverlayOut).filter((o): o is PlotOverlay => o !== null);
    return { ...planeConfig, xLabel, yLabel, overlays };
    // planeConfig is rebuilt every render; its fields are the real dependencies.
  }, [planeConfig?.xMin, planeConfig?.xMax, planeConfig?.xStep, planeConfig?.yMin, planeConfig?.yMax,
      planeConfig?.yStep, form.ppXLabel, form.ppYLabel, overlaysKey]);

  const targetShown = accuracy && preview && ppTargetOk(preview, form.ppTarget) ? form.ppTarget : null;
  const bandsKey = JSON.stringify(form.ppBands);
  const reveal = useMemo(() => {
    if (!targetShown) return null;
    const bands = form.ppBands
      .map((b) => ({ within: Number(b.within), points: Number(b.points) }))
      .filter((b) => Number.isInteger(b.within) && b.within >= 0 && b.points > 0);
    return { target: targetShown, bands };
  }, [targetShown?.x, targetShown?.y, bandsKey]);

  const setOverlay = (i: number, patch: Partial<PpOverlay>) =>
    onChange({ ppOverlays: form.ppOverlays.map((o, j) => (j === i ? { ...o, ...patch } : o)) });

  const axis = (name: 'x' | 'y') => {
    const min = name === 'x' ? 'ppXMin' : 'ppYMin';
    const max = name === 'x' ? 'ppXMax' : 'ppYMax';
    const step = name === 'x' ? 'ppXStep' : 'ppYStep';
    const label = name === 'x' ? 'ppXLabel' : 'ppYLabel';
    return (
      <div className="flex flex-wrap items-end gap-2">
        <span className="w-4 pb-2 text-sm font-semibold text-fg-muted">{name}</span>
        <div>
          <label className="block text-xs text-fg-muted mb-1">From</label>
          <Input type="number" step="any" aria-label={`${name} from`} value={form[min]}
            onChange={(e) => onChange({ [min]: e.target.value })} className="w-24 text-sm" />
        </div>
        <div>
          <label className="block text-xs text-fg-muted mb-1">To</label>
          <Input type="number" step="any" aria-label={`${name} to`} value={form[max]}
            onChange={(e) => onChange({ [max]: e.target.value })} className="w-24 text-sm" />
        </div>
        <div>
          <label className="block text-xs text-fg-muted mb-1">Step</label>
          <select className={SELECT} aria-label={`${name} step`} value={form[step]}
            onChange={(e) => onChange({ [step]: Number(e.target.value) })}>
            {PP_STEPS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-fg-muted mb-1">Axis label (optional)</label>
          <Input maxLength={PP_LABEL_MAX} placeholder={name} aria-label={`${name} axis label`} value={form[label]}
            onChange={(e) => onChange({ [label]: e.target.value })} className="w-32 text-sm" />
        </div>
      </div>
    );
  };

  const field = (o: PpOverlay, i: number, key: 'x' | 'y' | 'x1' | 'y1' | 'x2' | 'y2') => (
    <Input type="number" step="any" placeholder={key} aria-label={`Overlay ${i + 1} ${key}`} value={o[key]}
      onChange={(e) => setOverlay(i, { [key]: e.target.value })} className="w-20 text-sm" />
  );

  const problems = plotProblems(form, accuracy);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="block text-xs text-fg-muted">The plane (at most 20 cells per axis)</label>
        {axis('x')}
        {axis('y')}
      </div>

      <div>
        <label className="block text-xs text-fg-muted mb-2">
          Overlays: what the app draws for students to read (lines are extended across the plane)
        </label>
        <div className="space-y-2">
          {form.ppOverlays.map((o, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select className={SELECT} aria-label={`Overlay ${i + 1} kind`} value={o.kind}
                onChange={(e) => setOverlay(i, { kind: e.target.value as PpOverlayKind })}>
                <option value="point">Point</option>
                <option value="line">Line through two points</option>
                <option value="polynomial">Polynomial</option>
              </select>
              {o.kind === 'point' && <>{field(o, i, 'x')}{field(o, i, 'y')}</>}
              {o.kind === 'line' && (
                <>
                  <span className="text-xs text-fg-subtle">(</span>{field(o, i, 'x1')}{field(o, i, 'y1')}
                  <span className="text-xs text-fg-subtle">) to (</span>{field(o, i, 'x2')}{field(o, i, 'y2')}
                  <span className="text-xs text-fg-subtle">)</span>
                </>
              )}
              {o.kind === 'polynomial' && (
                <span className="flex items-center gap-1 text-xs text-fg-muted">
                  y =
                  {o.coefficients.map((c, k) => (
                    <span key={k} className="flex items-center gap-1">
                      {k > 0 && '+'}
                      <Input type="number" step="any" placeholder="0" aria-label={`Overlay ${i + 1} c${k}`} value={c}
                        onChange={(e) => {
                          const coefficients = [...o.coefficients] as PpOverlay['coefficients'];
                          coefficients[k] = e.target.value;
                          setOverlay(i, { coefficients });
                        }}
                        className="w-16 text-sm" />
                      {k === 1 ? 'x' : k === 2 ? 'x²' : k === 3 ? 'x³' : ''}
                    </span>
                  ))}
                </span>
              )}
              <Input maxLength={PP_LABEL_MAX} placeholder="label (optional)" aria-label={`Overlay ${i + 1} label`}
                value={o.label} onChange={(e) => setOverlay(i, { label: e.target.value })} className="w-36 text-sm" />
              <Button type="button" variant="ghost" size="sm" aria-label={`Remove overlay ${i + 1}`}
                onClick={() => onChange({ ppOverlays: form.ppOverlays.filter((_, j) => j !== i) })}>
                <Trash2 size={12} />
              </Button>
            </div>
          ))}
          {form.ppOverlays.length < PP_MAX_OVERLAYS && (
            <Button type="button" variant="outline" size="sm"
              onClick={() => onChange({ ppOverlays: [...form.ppOverlays, emptyOverlay('line')] })}>
              <Plus size={12} className="mr-1" /> Add overlay
            </Button>
          )}
        </div>
      </div>

      <div>
        <p className="text-xs text-fg-muted mb-2">
          {accuracy
            ? 'Preview: click it to set the target (snaps to the nearest grid point).'
            : 'Preview: what students see.'}
        </p>
        {preview ? (
          <PlotScatter
            config={preview}
            imageId={imageId}
            reveal={reveal}
            onPick={accuracy ? (p) => onChange({ ppTarget: gridToGraph(preview, p) }) : undefined}
            className="w-full max-w-lg h-96"
          />
        ) : (
          <p className="text-xs text-fg-subtle">Fix the plane above to see the preview.</p>
        )}
        {accuracy && (
          <p className="text-sm text-fg-muted mt-2" data-testid="plot-target">
            {form.ppTarget === null
              ? 'Target: not set'
              : targetShown && preview
                ? <>Target: <span className="text-success-text">{formatGridPoint(preview, graphToGrid(preview, targetShown))}</span></>
                : 'Target: no longer on the grid. Click the preview to choose a new one.'}
          </p>
        )}
        <p className="text-xs text-fg-subtle mt-1">
          Choose curves whose key points (a vertex, an intersection) lie on grid points, or use a finer
          step. A background image is stretched to the plane, so pick axis ranges whose shape matches it.
        </p>
      </div>

      {accuracy && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">
            Bands: an answer within N cells (counting squares, diagonals included) earns the points
          </label>
          <div className="flex gap-2 mb-1 px-0.5">
            <span className="w-28 text-xs text-fg-subtle">Within (cells)</span>
            <span className="w-24 text-xs text-fg-subtle">Points</span>
          </div>
          <div className="space-y-2">
            {form.ppBands.map((band, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input type="number" step="1" min="0" aria-label={`Band ${i + 1} within`} value={band.within}
                  onChange={(e) => onChange({ ppBands: form.ppBands.map((b, j) => (j === i ? { ...b, within: e.target.value } : b)) })}
                  className="w-28 text-sm" />
                <Input type="number" step="any" min="0" aria-label={`Band ${i + 1} points`} value={band.points}
                  onChange={(e) => onChange({ ppBands: form.ppBands.map((b, j) => (j === i ? { ...b, points: e.target.value } : b)) })}
                  className="w-24 text-sm" />
                {i === 0 && <span className="text-xs text-success-text">best band = correct</span>}
                {form.ppBands.length > 1 && (
                  <Button type="button" variant="ghost" size="sm"
                    onClick={() => onChange({ ppBands: form.ppBands.filter((_, j) => j !== i) })}>
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            {form.ppBands.length < PP_MAX_BANDS && (
              <Button type="button" variant="outline" size="sm"
                onClick={() => {
                  const last = form.ppBands[form.ppBands.length - 1];
                  const within = last ? String(Number(last.within) + 1) : '0';
                  const points = last ? String(Math.max(1, Math.floor(Number(last.points) / 2))) : '100';
                  onChange({ ppBands: [...form.ppBands, { within, points }] });
                }}>
                <Plus size={12} className="mr-1" /> Add band
              </Button>
            )}
          </div>
          <p className="text-xs text-fg-subtle mt-2">
            Question points (the best band): {form.ppBands[0]?.points || '—'}
          </p>
        </div>
      )}

      {problems.length > 0 && (
        <ul className="text-xs text-warning-text list-disc pl-5 space-y-0.5" data-testid="plot-problems">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
    </div>
  );
}
