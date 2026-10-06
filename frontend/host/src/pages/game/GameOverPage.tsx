import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { QuestionImage } from '../../components/ui/QuestionImage';
import { PromptText } from '../../components/PromptText';
import { Button } from '../../components/ui/button';
import type { AnswerReveal, HostQuestionSummaryItem } from '../../types/game';
import { buildNumericBars, withUnit, type NumericReveal } from '../../lib/numericEstimate';
import { PlotScatter } from '../../components/PlotScatter';
import { plotConfigOf, plotRevealOf, targetText } from '../../lib/plotPoint';

const TARGET_BUCKETS = 8;

interface Bucket {
  label: string;
  count: number;
  rangeStart: number;
  rangeEnd: number;
}

function chooseWidth(ceiling: number): number {
  const N = ceiling + 1;
  let bestW = 1;
  let bestDiff = Infinity;
  for (let w = 1; w * w <= N; w++) {
    if (N % w !== 0) continue;
    for (const cand of [w, N / w]) {
      const numBins = N / cand;
      if (numBins < 2) continue;
      const diff = Math.abs(numBins - TARGET_BUCKETS);
      if (diff < bestDiff) { bestDiff = diff; bestW = cand; }
    }
  }
  if (bestDiff > TARGET_BUCKETS) bestW = Math.max(1, Math.ceil(N / TARGET_BUCKETS));
  return bestW;
}

function buildBuckets(scores: number[], maxPossibleScore: number): Bucket[] {
  const ceiling = Math.max(maxPossibleScore, 1);
  const width = chooseWidth(ceiling);
  const numBuckets = Math.ceil((ceiling + 1) / width);
  const buckets: Bucket[] = Array.from({ length: numBuckets }, (_, i) => {
    const start = i * width;
    const end = Math.min(start + width - 1, ceiling);
    const label = start === end ? `${start}` : `${start}–${end}`;
    return { label, count: 0, rangeStart: start, rangeEnd: end };
  });
  for (const score of scores) {
    const idx = Math.min(Math.floor(score / width), numBuckets - 1);
    buckets[idx].count++;
  }
  return buckets;
}

// ---------------------------------------------------------------------------
// Per-question summary card
// ---------------------------------------------------------------------------

function optionLabel(i: number) { return String.fromCharCode(65 + i); }

function AnswerBar({ label, count, total, correct, colorClass }: {
  label: string; count: number; total: number; correct: boolean; colorClass: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className={`w-6 text-center font-bold text-sm shrink-0 ${correct ? 'text-success-text' : 'text-fg-muted'}`}>
        {label}
      </span>
      <div className="flex-1 h-6 bg-surface-raised rounded overflow-hidden">
        <div
          className={`h-full rounded transition-all duration-500 ${colorClass}`}
          style={{ width: `${Math.max(pct, count > 0 ? 2 : 0)}%` }}
        />
      </div>
      <span className={`w-8 text-right text-sm font-semibold shrink-0 ${correct ? 'text-success-text' : 'text-fg-muted'}`}>
        {count}
      </span>
      {correct && <span className="text-success-text text-xs font-bold shrink-0">✓</span>}
      {!correct && <span className="w-4 shrink-0" />}
    </div>
  );
}

function QuestionCard({ item, index }: { item: HostQuestionSummaryItem; index: number }) {
  const { type, gradingType, prompt, config, answerReveal, answerDistribution, totalAnswered, totalPlayers, correctCount, avgAnswerTimeMs, pointsValue } = item;

  const typeLabel: Record<string, string> = {
    multiple_choice: 'Multiple Choice',
    true_false: 'True / False',
    fill_in_the_blank: 'Fill in the Blank',
    multi_select: 'Multi-Select',
    numeric_estimate: 'Numeric Estimate',
    plot_point: 'Plot the Point',
  };

  // plot_point: a smaller class scatter; its image is the plane's background, not a prompt image.
  const plotConfig = type === 'plot_point' ? plotConfigOf(config) : null;
  const plotReveal = plotRevealOf(answerReveal);

  const answeredPct = totalPlayers > 0 ? Math.round((totalAnswered / totalPlayers) * 100) : 0;
  const correctPct = totalAnswered > 0 ? Math.round((correctCount / totalAnswered) * 100) : 0;

  const reveal = answerReveal as AnswerReveal;

  function isCorrectIndex(i: number): boolean {
    if (reveal.type === 'multiple_choice') {
      return (reveal as { type: 'multiple_choice'; correctIndices: number[] }).correctIndices.includes(i);
    }
    if (reveal.type === 'multi_select') {
      return ((reveal as { type: 'multi_select'; answerPoints: number[] }).answerPoints[i] ?? 0) > 0;
    }
    return false;
  }
  function isCorrectTF(val: 'true' | 'false'): boolean {
    if (reveal.type !== 'true_false') return false;
    const rv = reveal as { type: 'true_false'; correctValue: boolean };
    return val === 'true' ? rv.correctValue : !rv.correctValue;
  }

  return (
    <div className="w-full bg-surface border border-line rounded-2xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-fg-subtle text-xs uppercase tracking-widest font-semibold">
            Q{index + 1}
          </span>
          <span className="text-fg-subtle">·</span>
          <span className="text-fg-muted text-xs uppercase tracking-widest">
            {typeLabel[type] ?? type}
          </span>
          <span className="text-fg-subtle">·</span>
          <span className={`text-xs uppercase tracking-widest font-semibold ${gradingType === 'COMPLETENESS' ? 'text-warning-text' : 'text-accent-text'}`}>
            {gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
          </span>
          <span className="text-fg-subtle">·</span>
          <span className="text-fg-muted text-xs">{pointsValue} {pointsValue === 1 ? 'pt' : 'pts'}</span>
        </div>
        <div className="text-right text-xs text-fg-subtle shrink-0">
          <span className="text-fg-muted font-semibold">{totalAnswered}</span>/{totalPlayers} answered
          {avgAnswerTimeMs !== null && (
            <span className="ml-2 text-fg-subtle">· avg {(avgAnswerTimeMs / 1000).toFixed(1)}s</span>
          )}
        </div>
      </div>

      {/* Prompt */}
      <p className="text-fg text-lg font-semibold leading-snug"><PromptText prompt={prompt} /></p>
      {!plotConfig && (
        <QuestionImage imageId={config.image_id} alt="Image for the question" className="h-32 w-full max-w-sm" align="left" />
      )}

      {/* Distribution */}
      <div className="space-y-2">
        {(type === 'multiple_choice' || type === 'multi_select') && (config.options ?? []).map((opt, i) => {
          const count = answerDistribution[String(i)] ?? 0;
          const correct = isCorrectIndex(i);
          return (
            <div key={i} className="space-y-0.5">
              <div className="flex items-center gap-2 text-xs text-fg-muted">
                <span className={`font-bold ${correct ? 'text-success-text' : ''}`}>{optionLabel(i)}.</span>
                <QuestionImage
                  imageId={config.option_image_ids?.[i]}
                  alt={opt}
                  className="h-8 w-12 shrink-0"
                  fallbackText={null}
                />
                <span className={correct ? 'text-success-text' : ''}>{opt}</span>
              </div>
              <AnswerBar
                label={optionLabel(i)}
                count={count}
                total={totalPlayers}
                correct={correct}
                colorClass={correct ? 'bg-success' : 'bg-fg-subtle'}
              />
            </div>
          );
        })}

        {type === 'true_false' && (['true', 'false'] as const).map((val) => {
          const count = answerDistribution[val] ?? 0;
          const correct = isCorrectTF(val);
          return (
            <AnswerBar
              key={val}
              label={val === 'true' ? 'T' : 'F'}
              count={count}
              total={totalPlayers}
              correct={correct}
              colorClass={correct ? 'bg-success' : 'bg-danger'}
            />
          );
        })}

        {type === 'numeric_estimate' && reveal.type === 'numeric_estimate' && (
          <div className="space-y-2">
            <p className="text-fg text-base font-semibold">
              Target: <span className="text-success-text">{withUnit((reveal as NumericReveal).target, config.unit)}</span>
            </p>
            {buildNumericBars(reveal as NumericReveal, answerDistribution, config.unit).map((bar, i) => (
              <div key={i} className="space-y-0.5">
                <span className={`text-xs ${bar.correct ? 'text-success-text' : 'text-fg-muted'}`}>{bar.label}</span>
                <AnswerBar
                  label=""
                  count={bar.count}
                  total={totalPlayers}
                  correct={bar.correct === true}
                  colorClass={bar.correct ? 'bg-success' : 'bg-fg-subtle'}
                />
              </div>
            ))}
          </div>
        )}

        {plotConfig && (
          <div className="space-y-2">
            <p className="text-fg text-base font-semibold">
              {plotReveal ? (
                <>Target: <span className="text-success-text">{targetText(plotConfig, plotReveal)}</span></>
              ) : (
                'Class responses'
              )}
            </p>
            <PlotScatter
              config={plotConfig}
              imageId={config.image_id}
              distribution={answerDistribution}
              reveal={plotReveal}
              className="w-full max-w-md h-72"
            />
          </div>
        )}

        {type === 'fill_in_the_blank' && (
          <div className="space-y-2">
            {reveal.type === 'fill_in_the_blank' && (
              <p className="text-fg-muted text-sm">
                Accepted:{' '}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map((a, i, arr) => (
                  <span key={i}>
                    <span className="text-success-text font-mono">"{a}"</span>
                    {i < arr.length - 1 && <span className="text-fg-subtle">, </span>}
                  </span>
                ))}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance > 0 && (
                  <span className="text-fg-subtle ml-1">
                    (±{(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance} typo)
                  </span>
                )}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer stats */}
      <div className="flex items-center gap-4 pt-1 border-t border-line text-sm">
        {gradingType === 'ACCURACY' ? (
          <>
            <span className="text-success-text font-semibold">{correctCount} correct</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{correctPct}% accuracy</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{answeredPct}% responded</span>
          </>
        ) : (
          <>
            <span className="text-warning-text font-semibold">{totalAnswered} completed</span>
            <span className="text-fg-subtle">·</span>
            <span className="text-fg-muted">{answeredPct}% response rate</span>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GameOverPage() {
  const { gameOver } = useGame();
  const navigate = useNavigate();

  if (!gameOver) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-fg-muted">Loading final results…</p>
      </div>
    );
  }

  const { scores, playerCount, maxPossibleScore, questionSummary = [] } = gameOver;
  const buckets = buildBuckets(scores, maxPossibleScore);
  const maxCount = Math.max(...buckets.map(b => b.count), 1);

  const avg = scores.length > 0
    ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
    : 0;
  const high = scores.length > 0 ? Math.max(...scores) : 0;

  return (
    <div className="min-h-screen flex flex-col items-center p-8 gap-8">
      <div className="text-center">
        <h1 className="text-5xl font-black text-fg">Game Over!</h1>
        <p className="text-fg-muted mt-2">{playerCount} players · Max possible: {maxPossibleScore.toLocaleString()} pts</p>
      </div>

      {/* Histogram */}
      <div className="w-full max-w-3xl">
        <p className="text-fg-muted text-sm uppercase tracking-widest text-center mb-4">Score Distribution</p>
        <div className="flex items-end gap-2 h-48">
          {buckets.map((bucket, i) => {
            const heightPct = (bucket.count / maxCount) * 100;
            return (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span className="text-fg-muted text-sm font-semibold">
                  {bucket.count > 0 ? bucket.count : ''}
                </span>
                <div className="w-full bg-surface-raised rounded-t-lg relative" style={{ height: '160px' }}>
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-accent rounded-t-lg transition-all duration-700"
                    style={{ height: `${Math.max(heightPct, bucket.count > 0 ? 4 : 0)}%` }}
                  />
                </div>
                <span className="text-fg-subtle text-xs">{bucket.label}</span>
              </div>
            );
          })}
        </div>
        <p className="text-fg-subtle text-xs text-center mt-1">Score (points) →</p>
      </div>

      {/* Summary stats */}
      <div className="flex gap-12 text-center">
        <div>
          <p className="text-fg-muted text-xs uppercase tracking-widest">Average</p>
          <p className="text-fg text-2xl font-bold">{avg.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-fg-muted text-xs uppercase tracking-widest">High Score</p>
          <p className="text-fg text-2xl font-bold">{high.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-fg-muted text-xs uppercase tracking-widest">Players</p>
          <p className="text-fg text-2xl font-bold">{playerCount}</p>
        </div>
      </div>

      <Button onClick={() => navigate('/home')}>New Game</Button>

      {/* Per-question breakdown */}
      {questionSummary.length > 0 && (
        <div className="w-full max-w-3xl space-y-4 pb-8">
          <p className="text-fg-muted text-sm uppercase tracking-widest text-center">
            Question Breakdown
          </p>
          {questionSummary.map((item, i) => (
            <QuestionCard key={item.questionId} item={item} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
