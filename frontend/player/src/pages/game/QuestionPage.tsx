import { useRef, useState, useCallback, useMemo } from 'react';
import { useGame } from './GameLayout';
import { TimerBar } from '../../components/ui/TimerBar';
import { QuestionImage } from '../../components/ui/QuestionImage';
import { parseNumber } from '../../lib/parseNumber';
import { formatNumber } from '../../lib/numericEstimate';
import { plotConfigOf } from '../../lib/plotPoint';
import { PlotPointAnswer } from '../../components/PlotPointAnswer';

/** An option's text, with its image above it when the option has one (T8). While the
 * image loads a placeholder is shown; if it fails, the text alone remains. */
function OptionContent({ text, imageId }: { text: string; imageId?: string | null }) {
  if (!imageId) return <span>{text}</span>;
  return (
    <span className="flex flex-1 min-w-0 flex-col gap-2">
      <QuestionImage imageId={imageId} alt={text} className="h-28 w-28 mx-auto" fallbackText={null} />
      <span>{text}</span>
    </span>
  );
}

// Answer colours (docs/plans/t9-theming.md): the same in both themes, each with a text colour
// that passes AA on it, and a strong border so yellow and orange stand out on a light page. Written
// out in full: Tailwind only generates class names it can read literally.
const OPTION_COLORS = [
  'bg-option-1 text-on-option-1 border-line-strong',
  'bg-option-2 text-on-option-2 border-line-strong',
  'bg-option-3 text-on-option-3 border-line-strong',
  'bg-option-4 text-on-option-4 border-line-strong',
  'bg-option-5 text-on-option-5 border-line-strong',
  'bg-option-6 text-on-option-6 border-line-strong',
  'bg-option-7 text-on-option-7 border-line-strong',
  'bg-option-8 text-on-option-8 border-line-strong',
];

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i); // A, B, C, … Z
}

export default function QuestionPage() {
  const { currentQuestion, questionLocked, emitAnswer } = useGame();
  const startTimeRef = useRef(Date.now());
  const [submitted, setSubmitted] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());

  const toggleIndex = useCallback((i: number) => {
    if (submitted || questionLocked) return;
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }, [submitted, questionLocked]);

  // plot_point: one config object per question, so the canvas redraws only when it must.
  const plotConfig = useMemo(() => plotConfigOf(currentQuestion?.config), [currentQuestion?.config]);

  if (!currentQuestion) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-fg-muted">Loading question…</p>
      </div>
    );
  }

  function submit(answerData: Record<string, unknown>) {
    if (submitted) return;
    setSubmitted(true);
    emitAnswer(currentQuestion!.questionId, answerData, Date.now() - startTimeRef.current);
  }

  const questionLabel = (
    <p className="text-fg-muted text-sm text-center tracking-wide uppercase mb-1">
      Question {currentQuestion.questionNumber} of {currentQuestion.totalQuestions}
    </p>
  );

  const lockedMsg = (
    <p className="text-center text-warning-text text-sm mt-4 font-semibold">
      Answers locked — waiting for results…
    </p>
  );

  if (currentQuestion.type === 'multiple_choice') {
    const options = currentQuestion.config.options ?? [];
    return (
      <div className="py-6 px-4 flex flex-col gap-3">
        <div className="pb-2">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        {options.map((opt, i) => (
          <button
            key={i}
            disabled={submitted || questionLocked}
            onClick={() => submit({ selectedIndex: i })}
            className={`focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page w-full flex items-center gap-4 rounded-2xl px-5 py-4 text-left font-semibold text-lg border-2 transition-all
              ${submitted || questionLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-95 hover:[&:not(:active)]:brightness-95 active:brightness-90'}
              ${OPTION_COLORS[i % OPTION_COLORS.length]}`}
          >
            <span className="text-2xl font-black w-8 shrink-0">{optionLabel(i)}</span>
            <OptionContent text={opt} imageId={currentQuestion.config.option_image_ids?.[i]} />
          </button>
        ))}
        {submitted && <p className="text-center text-fg-muted text-sm mt-4">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'true_false') {
    return (
      <div className="min-h-screen flex flex-col justify-center p-4 gap-4">
        {questionLabel}
        <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: true })}
          className={`focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page w-full rounded-2xl py-8 bg-success text-on-success font-black text-3xl border-2 border-line-strong transition-all
            ${submitted || questionLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-95 hover:[&:not(:active)]:brightness-95 active:brightness-90'}`}
        >
          True
        </button>
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: false })}
          className={`focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page w-full rounded-2xl py-8 bg-danger text-on-danger font-black text-3xl border-2 border-line-strong transition-all
            ${submitted || questionLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-95 hover:[&:not(:active)]:brightness-95 active:brightness-90'}`}
        >
          False
        </button>
        {submitted && <p className="text-center text-fg-muted text-sm mt-2">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'fill_in_the_blank') {
    const maxLength = currentQuestion.config.maxLength ?? 100;
    return (
      <div className="min-h-screen flex flex-col justify-center p-4 gap-5">
        {questionLabel}
        <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />

        {submitted ? (
          <div className="flex flex-col items-center gap-3">
            <div className="text-5xl">🔒</div>
            <p className="text-fg text-xl font-bold">Answer locked in!</p>
            <p className="text-fg-muted text-base italic">"{inputValue.trim()}"</p>
            <p className="text-fg-subtle text-sm mt-2">Waiting for results…</p>
          </div>
        ) : questionLocked ? (
          <div className="flex flex-col items-center gap-3 mt-4">
            {lockedMsg}
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = inputValue.trim();
              if (trimmed) submit({ text: trimmed });
            }}
            className="flex flex-col gap-4"
          >
            <input
              type="text"
              maxLength={maxLength}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Type your answer…"
              autoFocus
              className="w-full rounded-xl px-4 py-4 text-fg text-xl bg-surface-raised border border-line-strong placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
            />
            <button
              type="submit"
              disabled={!inputValue.trim()}
              className="w-full rounded-2xl py-5 text-on-accent font-black text-2xl bg-accent hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit
            </button>
          </form>
        )}
      </div>
    );
  }

  if (currentQuestion.type === 'multi_select') {
    const options = currentQuestion.config.options ?? [];
    return (
      <div className="py-6 px-4 flex flex-col gap-3">
        <div className="pb-2">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <p className="text-center text-fg-muted text-sm">Select all that apply</p>
        {options.map((opt, i) => {
          const isSelected = selectedIndices.has(i);
          return (
            <button
              key={i}
              disabled={submitted || questionLocked}
              onClick={() => toggleIndex(i)}
              className={`focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page w-full flex items-center gap-4 rounded-2xl px-5 py-4 text-left font-semibold text-lg border-2 transition-all
                ${submitted || questionLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-95'}
                ${isSelected
                  ? 'bg-accent border-accent text-on-accent'
                  : 'bg-surface-raised border-line-strong text-fg'
                }`}
            >
              <span className={`text-xl font-black w-8 shrink-0 flex items-center justify-center rounded-md border-2 transition-colors
                ${isSelected ? 'border-on-accent text-on-accent' : 'border-line-strong text-fg-muted'}`}>
                {isSelected ? '✓' : optionLabel(i)}
              </span>
              <OptionContent text={opt} imageId={currentQuestion.config.option_image_ids?.[i]} />
            </button>
          );
        })}
        {!submitted && !questionLocked && (
          <button
            disabled={selectedIndices.size === 0}
            onClick={() => submit({ selectedIndices: Array.from(selectedIndices) })}
            className="w-full rounded-2xl py-5 text-on-accent font-black text-2xl bg-accent hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          >
            Submit ({selectedIndices.size} selected)
          </button>
        )}
        {submitted && <p className="text-center text-fg-muted text-sm mt-4">Answer submitted — waiting for results…</p>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'numeric_estimate') {
    const unit = currentQuestion.config.unit;
    const parsed = parseNumber(inputValue);
    const empty = inputValue.trim() === '';
    const canSubmit = parsed !== null && !submitted && !questionLocked;

    function toggleMinus() {
      setInputValue((v) => {
        const t = v.trim();
        return t.startsWith('-') ? t.slice(1) : `-${t}`;
      });
    }

    return (
      <div className="py-6 px-4 flex flex-col gap-4">
        <div className="pb-2">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>

        {submitted ? (
          <div className="flex flex-col items-center gap-3">
            <div className="text-5xl">🔒</div>
            <p className="text-fg text-xl font-bold">Answer locked in!</p>
            {parsed !== null && (
              <p className="text-fg-muted text-base italic">
                {formatNumber(parsed)}{unit ? ` ${unit}` : ''}
              </p>
            )}
            <p className="text-fg-subtle text-sm mt-2">Waiting for results…</p>
          </div>
        ) : questionLocked ? (
          <div className="flex flex-col items-center gap-3 mt-4">{lockedMsg}</div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (parsed !== null) submit({ value: parsed });
            }}
            className="flex flex-col gap-3"
          >
            <p className="text-center text-fg-muted text-sm">Enter your best estimate</p>
            <div className="flex items-stretch gap-2">
              <button
                type="button"
                onClick={toggleMinus}
                aria-label="Toggle minus sign"
                className="w-14 shrink-0 rounded-xl bg-surface-raised border border-line-strong text-fg text-2xl font-black active:scale-95 focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
              >
                ±
              </button>
              <input
                type="text"
                inputMode="decimal"
                autoComplete="off"
                autoFocus
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="0"
                aria-label="Your estimate"
                className="min-w-0 flex-1 rounded-xl px-4 py-4 text-fg text-2xl bg-surface-raised border border-line-strong placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
              />
              {unit && <span className="self-center text-fg-muted text-lg shrink-0">{unit}</span>}
            </div>
            <p className={`text-center text-sm min-h-5 ${parsed === null && !empty ? 'text-warning-text' : 'text-fg-muted'}`}>
              {parsed !== null
                ? `= ${formatNumber(parsed)}${unit ? ` ${unit}` : ''}`
                : empty ? '' : 'Enter a number'}
            </p>
            <button
              type="submit"
              disabled={!canSubmit}
              className="w-full rounded-2xl py-5 text-on-accent font-black text-2xl bg-accent hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit
            </button>
          </form>
        )}
      </div>
    );
  }

  if (currentQuestion.type === 'plot_point' && plotConfig) {
    return (
      <PlotPointAnswer
        key={currentQuestion.questionId}
        config={plotConfig}
        imageId={currentQuestion.config.image_id}
        locked={questionLocked}
        submitted={submitted}
        onSubmit={({ col, row }) => submit({ col, row })}
        header={
          <div>
            {questionLabel}
            <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
          </div>
        }
        status={
          submitted ? (
            <p className="text-center text-fg-muted text-sm">Answer submitted — waiting for results…</p>
          ) : questionLocked ? (
            lockedMsg
          ) : null
        }
      />
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <p className="text-fg-muted">Unsupported question type.</p>
    </div>
  );
}
