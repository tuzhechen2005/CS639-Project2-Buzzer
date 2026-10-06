/** A question's client-visible config. Image ids follow the T8 convention
 * (docs/plans/t8-image-support.md §E): `option_image_ids` is parallel to `options`. */
export interface QuestionConfig {
  options?: string[];
  maxLength?: number;
  unit?: string; // numeric_estimate
  image_id?: string | null;
  option_image_ids?: (string | null)[];
}

export interface PlayerInfo {
  userId: string;
  displayName: string;
}

export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  players: PlayerInfo[];
  playerCount: number;
  questionPhase?: 'QUESTION' | 'RESULTS' | null;
  currentQuestion?: QuestionPayload | null;
  questionLocked?: boolean;
  timerRemainingSeconds?: number | null;
}

export interface PlayerJoinedPayload {
  userId: string;
  displayName: string;
  playerCount: number;
}

export interface PlayerLeftPayload {
  userId: string;
  playerCount: number;
}

export type QuestionType =
  | 'multiple_choice'
  | 'true_false'
  | 'fill_in_the_blank'
  | 'multi_select'
  | 'numeric_estimate';

export interface QuestionPayload {
  questionId: number;
  questionNumber: number;
  totalQuestions: number;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  prompt: string;
  config: QuestionConfig;
  timeLimitSeconds: number;
  pointsValue: number;
  editDistance?: number;
  startedAt?: string;  // ISO timestamp — only present in sync_state reconnect payloads
}

export interface AnswerStatusPayload {
  userId: string;
  displayName: string;
  answered: boolean;
  answeredCount: number;
  totalPlayers: number;
}

export interface AnswerPhaseEndedPayload {
  questionId: number;
  answeredCount: number;
  totalPlayers: number;
  allAnswered?: boolean; // true only when every player answered (not just timer expiry)
}

export interface LeaderboardEntry {
  userId: string;
  displayName: string;
  score: number;
  rank: number;
}

export type AnswerReveal =
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
  | Record<string, never>;

export interface HostResultsPayload {
  questionId: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  totalAnswered: number;
  totalPlayers: number;
}

export interface HostQuestionSummaryItem {
  questionId: number;
  questionNumber: number;
  prompt: string;
  type: QuestionType;
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: QuestionConfig;
  pointsValue: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  totalAnswered: number;
  totalPlayers: number;
  correctCount: number;
  avgAnswerTimeMs: number | null;
}

export interface HostGameOverPayload {
  scores: number[];
  playerCount: number;
  maxPossibleScore: number;
  questionSummary: HostQuestionSummaryItem[];
}

export type HostPhase = 'lobby' | 'question' | 'results' | 'gameover';
