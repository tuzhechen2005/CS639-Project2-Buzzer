import { useEffect, useRef, useState, type ReactNode } from 'react';
import { PlotCanvas } from './PlotCanvas';
import { formatGridPoint, type GridPoint, type PlotConfig } from '../lib/plotGeometry';
import {
  EMPTY_TYPED,
  canSubmitTyped,
  commitAxis,
  commitForSubmit,
  flipSign,
  placedOnCanvas,
  type TypedState,
} from '../lib/plotPoint';

interface PlotPointAnswerProps {
  config: PlotConfig;
  imageId?: string | null;
  locked: boolean;
  submitted: boolean;
  onSubmit: (p: GridPoint) => void;
  /** Question number and timer, shown above the canvas (portrait) or beside it (landscape). */
  header: ReactNode;
  /** The "answers locked" / "submitted" message. */
  status: ReactNode;
}

/** Landscape = wider than tall: the controls move to a column right of the canvas. */
function useLandscape(): boolean {
  const query = '(orientation: landscape)';
  const [landscape, setLandscape] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setLandscape(mql.matches);
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);
  return landscape;
}

/**
 * The plot_point answer screen (docs/plans/t7-plot-the-point.md, P6): the canvas is the main
 * input; typed coordinates sit behind a collapsed "Type coordinates" toggle. The rules for the
 * typed fields live in lib/plotPoint.ts. The point is kept across lock and unlock.
 */
export function PlotPointAnswer({ config, imageId, locked, submitted, onSubmit, header, status }: PlotPointAnswerProps) {
  const landscape = useLandscape();
  const [typed, setTypedState] = useState<TypedState>(EMPTY_TYPED);
  const [panelOpen, setPanelOpen] = useState(false);
  // The latest state, so Submit right after a blur commit never reads a stale render.
  const typedRef = useRef(typed);
  const setTyped = (next: TypedState) => {
    typedRef.current = next;
    setTypedState(next);
  };
  const inactive = locked || submitted;

  const commit = (axis: 'x' | 'y') => {
    if (inactive) return;
    setTyped(commitAxis(config, typedRef.current, axis));
  };

  const setText = (axis: 'x' | 'y', text: string) => {
    const s = typedRef.current;
    setTyped(axis === 'x' ? { ...s, xText: text } : { ...s, yText: text });
  };

  const flip = (axis: 'x' | 'y') => {
    if (inactive) return;
    const s = typedRef.current;
    const text = axis === 'x' ? s.xText : s.yText;
    const flipped = flipSign(text);
    const next = axis === 'x' ? { ...s, xText: flipped } : { ...s, yText: flipped };
    // On an empty field, ± only inserts "−"; otherwise it commits at once.
    setTyped(text.trim() === '' ? next : commitAxis(config, next, axis));
  };

  const submit = () => {
    if (inactive) return;
    const next = commitForSubmit(config, typedRef.current);
    setTyped(next);
    if (next.point) onSubmit(next.point);
  };

  const readout = typed.point
    ? formatGridPoint(config, typed.point)
    : typed.needBoth
      ? 'Enter both coordinates'
      : 'Tap the grid';

  const field = (axis: 'x' | 'y') => (
    <div className="flex items-stretch gap-2">
      <span className="self-center w-5 text-fg-muted font-semibold">{axis}</span>
      <button
        type="button"
        disabled={inactive}
        onClick={() => flip(axis)}
        aria-label={`Toggle minus sign on ${axis}`}
        className="w-12 shrink-0 rounded-xl bg-surface-raised border border-line-strong text-fg text-xl font-black active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
      >
        ±
      </button>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        disabled={inactive}
        value={axis === 'x' ? typed.xText : typed.yText}
        onChange={(e) => setText(axis, e.target.value)}
        onBlur={() => commit(axis)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            commit(axis);
          }
        }}
        aria-label={`${axis} coordinate`}
        className="min-w-0 flex-1 rounded-xl px-3 py-2 text-fg text-xl bg-surface-raised border border-line-strong placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page disabled:opacity-50 disabled:cursor-not-allowed"
      />
    </div>
  );

  const controls = (
    <div className="flex flex-col gap-2">
      <p aria-live="polite" className="text-center text-fg text-xl font-bold min-h-7">
        {readout}
      </p>
      {!submitted && (
        <button
          type="button"
          disabled={inactive || !canSubmitTyped(typed)}
          onClick={submit}
          className="w-full rounded-2xl py-4 text-on-accent font-black text-2xl bg-accent hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Submit
        </button>
      )}
      {status}
      {!submitted && (
        <button
          type="button"
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen((o) => !o)}
          className="min-h-11 px-3 rounded-xl text-accent-text text-sm underline self-center focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
        >
          {panelOpen ? 'Hide coordinates' : 'Type coordinates'}
        </button>
      )}
      {!submitted && panelOpen && (
        <div className="flex flex-col gap-2">
          {field('x')}
          {field('y')}
        </div>
      )}
    </div>
  );

  const canvas = (className: string) => (
    <PlotCanvas
      className={className}
      config={config}
      imageId={imageId}
      point={typed.point}
      onPoint={(p) => !inactive && setTyped(placedOnCanvas(config, p))}
      disabled={inactive}
    />
  );

  // One layout tree for both orientations: header, canvas and controls always stay in the same
  // places, and only their classes change. Swapping two trees on rotation would remount the
  // timer (restarting it at full time) and the canvas (dropping a drag).
  // Portrait: a column; with the panel closed everything fits the screen, open the page may
  // scroll. Landscape: a grid with the canvas on the left at full height and the header and
  // controls in a column on the right.
  return (
    <div
      className={
        landscape
          ? 'h-[100dvh] grid grid-cols-[minmax(0,1fr)_16rem] grid-rows-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 p-3'
          : `flex flex-col gap-2 p-3 ${panelOpen ? 'min-h-[100dvh]' : 'h-[100dvh]'}`
      }
    >
      <div className={landscape ? 'col-start-2 row-start-1' : ''}>{header}</div>
      {canvas(
        landscape
          ? 'col-start-1 row-start-1 row-span-2 h-full'
          : panelOpen
            ? 'w-full h-[60dvh] shrink-0'
            : 'w-full flex-1',
      )}
      <div className={landscape ? 'col-start-2 row-start-2 min-h-0 overflow-y-auto' : ''}>{controls}</div>
    </div>
  );
}
