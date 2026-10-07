import { useEffect, useMemo, useState } from 'react';
import { Check } from 'lucide-react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { QuestionImage } from '../../components/ui/QuestionImage';
import { PromptText } from '../../components/PromptText';
import type { AnswerReveal, QuestionConfig } from '../../types/game';
import { buildNumericBars, withUnit, type NumericReveal } from '../../lib/numericEstimate';
import { PlotScatter } from '../../components/PlotScatter';
import { plotConfigOf, plotRevealOf, targetText } from '../../lib/plotPoint';

const RESULTS_DISPLAY_SECONDS = 10;

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i);
}

// ---------------------------------------------------------------------------
// Levenshtein distance — used to colour word-cloud entries for FITB questions
// ---------------------------------------------------------------------------

function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

// ---------------------------------------------------------------------------
// Word Cloud — for fill_in_the_blank questions
// ---------------------------------------------------------------------------

interface WordCloudProps {
  distribution: Record<string, number>;
  answerReveal: AnswerReveal;
  totalAnswered: number;
  totalPlayers: number;
}

function WordCloud({ distribution, answerReveal, totalAnswered, totalPlayers }: WordCloudProps) {
  const entries = Object.entries(distribution).sort(([, a], [, b]) => b - a);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const isAccuracy =
    'type' in answerReveal && answerReveal.type === 'fill_in_the_blank';
  const acceptedAnswers: string[] =
    isAccuracy && 'acceptedAnswers' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map(a => a.toLowerCase())
      : [];
  const editDistance: number =
    isAccuracy && 'editDistance' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance
      : 0;

  function sizeClass(count: number): string {
    const f = count / maxCount;
    if (f > 0.75) return 'text-5xl font-black';
    if (f > 0.5)  return 'text-4xl font-bold';
    if (f > 0.25) return 'text-3xl font-semibold';
    if (f > 0.1)  return 'text-2xl font-medium';
    return 'text-xl';
  }

  function isCorrectWord(word: string): boolean {
    if (!isAccuracy || acceptedAnswers.length === 0) return false;
    return acceptedAnswers.some(a => levenshtein(word.toLowerCase(), a) <= editDistance);
  }

  return (
    <div className="w-full max-w-3xl flex flex-col gap-4">
      {isAccuracy && acceptedAnswers.length > 0 && (
        <p className="text-center text-fg-muted text-xl">
          Correct answer:{' '}
          <span className="text-success-text font-semibold">
            {(answerReveal as { acceptedAnswers: string[] }).acceptedAnswers.join(' / ')}
            {editDistance > 0 && (
              <span className="text-fg-subtle font-normal ml-1">(±{editDistance})</span>
            )}
          </span>
        </p>
      )}

      <div className="flex flex-wrap gap-x-5 gap-y-3 justify-center items-center min-h-32 p-4 bg-surface rounded-2xl">
        {entries.map(([word, count]) => (
          <span
            key={word}
            title={`${count} player${count !== 1 ? 's' : ''}`}
            className={`${sizeClass(count)} transition-colors ${
              isCorrectWord(word) ? 'text-success-text' : 'text-fg-muted'
            }`}
          >
            {/* Not colour alone: a correct word also gets a check mark and a spoken label. */}
            {isCorrectWord(word) && (
              <>
                <Check aria-hidden className="inline h-[0.75em] w-[0.75em] mr-1 align-baseline" strokeWidth={3} />
                <span className="sr-only">Correct: </span>
              </>
            )}
            {word}
          </span>
        ))}
        {entries.length === 0 && (
          <p className="text-fg-subtle text-xl">No answers submitted</p>
        )}
      </div>

      <p className="text-fg-muted text-xl text-right">
        {totalAnswered} / {totalPlayers} answered
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bar Chart — for multiple_choice and true_false
// ---------------------------------------------------------------------------

interface BarChartProps {
  bars: { label: string; count: number; correct: boolean | null; imageId?: string | null; imageAlt?: string }[];
  totalAnswered: number;
  totalPlayers: number;
}

function AnswerBarChart({ bars, totalAnswered, totalPlayers, wideLabels }: BarChartProps & { wideLabels?: boolean }) {
  const maxCount = Math.max(...bars.map(b => b.count), 1);
  // Keep the bars aligned when only some options have a picture.
  const anyImage = bars.some(b => b.imageId);

  return (
    <div className="w-full max-w-4xl space-y-3">
      {bars.map((bar, i) => {
        const pct = Math.round((bar.count / maxCount) * 100);
        // Fill and the count printed inside it (docs/plans/t9-theming.md, host result bars).
        const barColor =
          bar.correct === true
            ? 'bg-success'
            : bar.correct === false
            ? 'bg-fg-subtle'
            : 'bg-accent';
        const countColor =
          bar.correct === true
            ? 'text-on-success'
            : bar.correct === false
            ? 'text-surface'
            : 'text-on-accent';

        return (
          <div key={i} className="flex items-center gap-3">
            <span
              title={bar.label}
              className={`text-xl font-semibold text-right truncate shrink-0 ${wideLabels ? 'w-56' : 'w-48'} ${bar.correct === true ? 'text-success-text' : 'text-fg-muted'}`}
            >
              {bar.label}
            </span>
            {anyImage && (
              <span className="h-10 w-14 shrink-0">
                <QuestionImage
                  imageId={bar.imageId}
                  alt={bar.imageAlt ?? bar.label}
                  className="h-full w-full"
                  fallbackText={null}
                />
              </span>
            )}
            <div className="flex-1 bg-surface-raised rounded-full h-12 overflow-hidden">
              {/* No fill at all for zero answers: padding alone would draw a stub. */}
              {bar.count > 0 && (
                <div
                  className={`h-full min-w-16 rounded-full flex items-center justify-end pr-4 transition-all duration-500 ${barColor}`}
                  style={{ width: `${pct}%` }}
                >
                  <span className={`text-2xl font-semibold tabular-nums ${countColor}`}>{bar.count}</span>
                </div>
              )}
            </div>
            {/* One fixed-width column, so every track has the same length. */}
            <span className="w-40 shrink-0 inline-flex items-center gap-3">
              {bar.count === 0 && (
                <span className="text-fg-muted text-2xl font-semibold tabular-nums">0</span>
              )}
              {bar.correct === true && (
                <span className="text-success-text text-xl font-semibold inline-flex items-center gap-1">
                  <Check aria-hidden className="h-5 w-5" strokeWidth={3} /> Correct
                </span>
              )}
            </span>
          </div>
        );
      })}

      <p className="text-fg-muted text-xl text-right pt-1">
        {totalAnswered} / {totalPlayers} answered
      </p>
    </div>
  );
}

function buildBars(
  reveal: AnswerReveal,
  distribution: Record<string, number>,
  config: QuestionConfig | undefined,
): BarChartProps['bars'] {
  const options = config?.options;
  const image = (i: number, opt: string) => ({ imageId: config?.option_image_ids?.[i], imageAlt: opt });
  if (reveal.type === 'multiple_choice') {
    const opts = options ?? [];
    return opts.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: reveal.correctIndices.includes(i),
      ...image(i, opt),
    }));
  }

  if (reveal.type === 'multi_select') {
    const opts = options ?? [];
    return opts.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: (reveal.answerPoints[i] ?? 0) > 0,
      ...image(i, opt),
    }));
  }

  if (reveal.type === 'true_false') {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: reveal.correctValue === true },
      { label: 'False', count: distribution['false'] ?? 0, correct: reveal.correctValue === false },
    ];
  }

  // completeness (non-FITB) — no right/wrong
  if (options && options.length > 0) {
    return options.map((opt, i) => ({
      label: `${optionLabel(i)}  ${opt}`,
      count: distribution[String(i)] ?? 0,
      correct: null,
      ...image(i, opt),
    }));
  }

  if ('true' in distribution || 'false' in distribution) {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: null },
      { label: 'False', count: distribution['false'] ?? 0, correct: null },
    ];
  }

  return [];
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsPage() {
  const { questionResults, currentQuestion, autoAdvance, emitAdvance } = useGame();
  const [countdown, setCountdown] = useState(RESULTS_DISPLAY_SECONDS);

  const isLast = currentQuestion
    ? currentQuestion.questionNumber >= currentQuestion.totalQuestions
    : false;

  useEffect(() => {
    if (!autoAdvance) return;
    setCountdown(RESULTS_DISPLAY_SECONDS);
    const interval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(interval); emitAdvance(); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [autoAdvance, questionResults, emitAdvance]);

  const isFitb = currentQuestion?.type === 'fill_in_the_blank';
  const isNumeric = currentQuestion?.type === 'numeric_estimate';
  // plot_point: a class scatter instead of bars (P7).
  const plotConfig = useMemo(
    () => (currentQuestion?.type === 'plot_point' ? plotConfigOf(currentQuestion.config) : null),
    [currentQuestion],
  );
  const plotReveal = plotRevealOf(questionResults?.answerReveal);
  const unit = currentQuestion?.config?.unit;
  const numericReveal =
    isNumeric && questionResults?.answerReveal.type === 'numeric_estimate'
      ? (questionResults.answerReveal as NumericReveal)
      : null;

  const bars =
    numericReveal && questionResults
      ? buildNumericBars(numericReveal, questionResults.answerDistribution, unit)
      : !isFitb && !isNumeric && !plotConfig && questionResults
      ? buildBars(
          questionResults.answerReveal,
          questionResults.answerDistribution,
          currentQuestion?.config,
        )
      : [];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-8">
      <h2 className="text-3xl font-bold text-fg">
        Question {currentQuestion?.questionNumber} Results
      </h2>

      {currentQuestion && (
        <p className="text-fg-muted text-xl text-center max-w-2xl">
          <PromptText prompt={currentQuestion.prompt} />
        </p>
      )}

      {currentQuestion && !plotConfig && (
        <QuestionImage
          imageId={currentQuestion.config.image_id}
          alt="Image for the question"
          className="w-full max-w-md h-40"
        />
      )}

      {questionResults && plotConfig ? (
        <>
          {plotReveal ? (
            <p className="text-fg text-3xl font-bold">
              Target: <span className="text-success-text">{targetText(plotConfig, plotReveal)}</span>
            </p>
          ) : (
            <p className="text-fg-muted text-xl font-semibold">Class responses</p>
          )}
          <PlotScatter
            config={plotConfig}
            imageId={currentQuestion?.config.image_id}
            distribution={questionResults.answerDistribution}
            reveal={plotReveal}
            scale={1.5}
            className="w-full max-w-4xl h-[60vh]"
          />
          <p className="text-fg-muted text-xl">
            {questionResults.totalAnswered} / {questionResults.totalPlayers} answered
          </p>
        </>
      ) : questionResults && isFitb ? (
        <WordCloud
          distribution={questionResults.answerDistribution}
          answerReveal={questionResults.answerReveal}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
      ) : questionResults ? (
        <>
        {numericReveal && (
          <p className="text-fg text-3xl font-bold">
            Target: <span className="text-success-text">{withUnit(numericReveal.target, unit)}</span>
          </p>
        )}
        <AnswerBarChart
          wideLabels={numericReveal !== null}
          bars={bars}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
        </>
      ) : null}

      <div className="flex flex-col items-center gap-2">
        <Button size="lg" onClick={emitAdvance} className="px-10">
          {isLast ? 'Show Final Results' : 'Next Question'}
        </Button>
        {autoAdvance && (
          <p className="text-fg-muted text-xl tabular-nums">
            Auto-advancing in {countdown}s
          </p>
        )}
      </div>
    </div>
  );
}
