/** A question's client-visible config. Image ids follow the T8 convention
 * (docs/plans/t8-image-support.md §E): `option_image_ids` is parallel to `options`. */
export interface QuestionConfig {
  options?: string[];
  maxLength?: number;
  unit?: string; // numeric_estimate
  image_id?: string | null;
  option_image_ids?: (string | null)[];
  // plot_point (docs/plans/t7-plot-the-point.md): the plane and what is drawn on it
  xMin?: number;
  xMax?: number;
  xStep?: number;
  yMin?: number;
  yMax?: number;
  yStep?: number;
  xLabel?: string | null;
  yLabel?: string | null;
  overlays?: PlotOverlayConfig[] | null;
}

/** An overlay drawn on a plot_point plane: a point, an infinite line through two points, or a
 * polynomial y = c0 + c1 x + c2 x^2 + c3 x^3. */
export interface PlotOverlayConfig {
  kind: string;
  x?: number;
  y?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  coefficients?: number[];
  label?: string | null;
}

export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  playerCount: number;
  questionLocked?: boolean;
}

export interface PlayerJoinedPayload {
  playerCount: number;
}

export type QuestionType =
  | 'multiple_choice'
  | 'true_false'
  | 'fill_in_the_blank'
  | 'multi_select'
  | 'numeric_estimate'
  | 'plot_point';

export interface QuestionPayload {
  questionId: number;
  questionNumber: number;
  totalQuestions: number;
  type: QuestionType;
  prompt: string;
  config: QuestionConfig;
  timeLimitSeconds: number;
  pointsValue: number;
}

export interface AnswerResultPayload {
  questionId: number;
  isCorrect: boolean;
  pointsAwarded: number;
  totalScore: number;
  alreadyAnswered?: boolean;
}

export type PlayerAnswerReveal =
  | { type: 'multiple_choice'; correctIndices: number[] }
  | { type: 'true_false'; correctValue: boolean }
  | { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }
  | { type: 'completeness' }
  | { type: 'multi_select'; answerPoints: number[] }
  | {
      type: 'numeric_estimate';
      target: number;
      mode: 'relative' | 'absolute';
      bands: { within: number; points: number }[];
    }
  | {
      type: 'plot_point';
      target: { x: number; y: number };
      bands: { within: number; points: number }[];
    };

export interface PlayerResultsPayload {
  questionId: number;
  answerReveal: PlayerAnswerReveal;
  yourPoints: number;
  yourScore: number;
  yourRank: number;
  playerCount: number;
}

export interface QuestionSummaryItem {
  questionId: number;
  prompt: string;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: QuestionConfig;
  pointsAwarded: number;
  maxPoints: number;
  answerTimeMs: number | null;
  playerAnswer: {
    selectedIndex?: number;
    selectedValue?: boolean;
    text?: string;
    selectedIndices?: number[];
    value?: number;
    col?: number; // plot_point: the grid point the player submitted
    row?: number;
  } | null;
  answerReveal: PlayerAnswerReveal;
}

export interface PlayerGameOverPayload {
  yourFinalScore: number;
  yourFinalRank: number;
  playerCount: number;
  questionSummary: QuestionSummaryItem[];
}

export type PlayerPhase = 'lobby' | 'question' | 'feedback' | 'results' | 'gameover';
