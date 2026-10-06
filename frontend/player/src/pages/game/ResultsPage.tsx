import { useGame } from './GameLayout';
import {
  differenceLine, formatNumber, numericVerdict, outcomeLine, withUnit,
} from '../../lib/numericEstimate';
import { gridPointOf, plotConfigOf, plotResultLine, plotVerdict } from '../../lib/plotPoint';

function describeAnswer(
  lastAnswerData: Record<string, unknown> | null,
  type: string,
  options: string[] | undefined,
): string | null {
  if (!lastAnswerData) return null;
  if (type === 'multiple_choice') {
    const idx = lastAnswerData.selectedIndex;
    if (typeof idx === 'number' && options && options[idx] !== undefined) {
      return `${String.fromCharCode(65 + idx)} — ${options[idx]}`;
    }
  }
  if (type === 'true_false') {
    return lastAnswerData.selectedValue ? 'True' : 'False';
  }
  if (type === 'fill_in_the_blank') {
    return typeof lastAnswerData.text === 'string' ? lastAnswerData.text : null;
  }
  if (type === 'numeric_estimate') {
    return typeof lastAnswerData.value === 'number' ? formatNumber(lastAnswerData.value) : null;
  }
  return null;
}

export default function ResultsPage() {
  const { questionResults, currentQuestion, lastAnswerData } = useGame();

  if (!questionResults) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-slate-400">Loading results…</p>
      </div>
    );
  }

  const { answerReveal, yourPoints, yourScore, yourRank, playerCount } = questionResults;
  const answeredLabel = describeAnswer(
    lastAnswerData,
    currentQuestion?.type ?? '',
    currentQuestion?.config.options,
  );
  const isCompleteness = answerReveal.type === 'completeness';
  const isFitb = answerReveal.type === 'fill_in_the_blank';
  const numericReveal = answerReveal.type === 'numeric_estimate' ? answerReveal : null;
  // plot_point: one line with both points, the distance and the points (P6).
  const plotConfig = currentQuestion?.type === 'plot_point' ? plotConfigOf(currentQuestion.config) : null;
  const plotReveal = answerReveal.type === 'plot_point' ? answerReveal : null;
  const plotLine = plotConfig
    ? plotResultLine(plotConfig, plotReveal, gridPointOf(lastAnswerData), yourPoints)
    : '';
  const verdict = numericReveal
    ? numericVerdict(numericReveal, yourPoints)
    : plotReveal
      ? plotVerdict(plotReveal, yourPoints)
      : null;
  const unit = currentQuestion?.config.unit;
  const guess =
    lastAnswerData && typeof lastAnswerData.value === 'number' ? lastAnswerData.value : null;
  const isCorrect = !isCompleteness && yourPoints > 0;

  const fitbAccepted: string[] =
    isFitb && 'acceptedAnswers' in answerReveal ? answerReveal.acceptedAnswers : [];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 gap-5 text-center">

      {/* Correct / Wrong / Recorded */}
      {isCompleteness ? (
        <p className="text-indigo-400 text-4xl font-black">Answer recorded!</p>
      ) : verdict === 'close' ? (
        <p className="text-amber-400 text-4xl font-black">Close!</p>
      ) : verdict === 'correct' || (verdict === null && isCorrect) ? (
        <p className="text-green-400 text-4xl font-black">Correct!</p>
      ) : (
        <p className="text-red-400 text-4xl font-black">Incorrect</p>
      )}

      {/* What the player answered */}
      {answeredLabel && (
        <p className="text-slate-400 text-base">
          You answered: <span className="text-slate-200 font-semibold">{answeredLabel}</span>
        </p>
      )}

      {/* Plot the point: "You: (4, −2) · Target: (3, −2) · 1 cell off · 50 pts" */}
      {plotLine && <p className="text-slate-300 text-base font-semibold">{plotLine}</p>}

      {/* Correct answer for FITB ACCURACY */}
      {isFitb && fitbAccepted.length > 0 && (
        <p className="text-slate-400 text-base">
          Correct: <span className="text-green-400 font-semibold">{fitbAccepted.join(' / ')}</span>
        </p>
      )}

      {/* Numeric estimate: the target, how far off, and the band the server gave points for */}
      {numericReveal && (
        <div className="space-y-1">
          <p className="text-slate-400 text-base">
            Target: <span className="text-green-400 font-semibold">{withUnit(numericReveal.target, unit)}</span>
          </p>
          {guess !== null && (
            <p className="text-slate-400 text-base">{differenceLine(guess, numericReveal.target, unit)}</p>
          )}
          <p className="text-slate-300 text-base font-semibold">
            {outcomeLine(numericReveal, yourPoints, unit)}
          </p>
        </div>
      )}

      {/* Points for this question */}
      <p className="text-slate-100 text-3xl font-bold">
        +{yourPoints.toLocaleString()} pts
      </p>

      {/* Running total and rank */}
      <div className="mt-2 space-y-1">
        <p className="text-slate-300 text-lg">
          Total: <span className="font-bold text-white">{yourScore.toLocaleString()}</span> pts
        </p>
        <p className="text-slate-400 text-base">
          Rank <span className="font-bold text-white">#{yourRank}</span> of {playerCount}
        </p>
      </div>

      <p className="text-slate-500 text-sm mt-4">Waiting for next question…</p>
    </div>
  );
}
