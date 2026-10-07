import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Trash2, ChevronUp, ChevronDown, Download, Copy, Lock, Pencil } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { ImageLibraryPanel, ImagePicker, useImageLibrary, type ImageLibraryState } from './ImageLibrary';
import { QuestionImage } from '../../components/ui/QuestionImage';
import { PromptText } from '../../components/PromptText';
import {
  PP_DEFAULT_TIME, PlotPointFields, buildPpPayload, plotProblems, ppDefaultForm, ppFromQuestion,
  ppListSummary, ppPointsValue, type PpForm,
} from './PlotPointEditor';

/** A game as the course routes return it (the host app declares the same shape in GamesTab). */
export interface Game {
  id: number;
  course_id: number;
  title: string;
  description: string;
  max_players: number;
  created_at: string;
  locked: boolean;
}

type QuestionType =
  | 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'numeric_estimate' | 'plot_point';
type GradingType = 'ACCURACY' | 'COMPLETENESS';

interface Question {
  id: number;
  type: QuestionType;
  grading_type: GradingType;
  prompt: string;
  config: Record<string, unknown>;
  answer_data: Record<string, unknown>;
  time_limit_seconds: number;
  points_value: number;
  order_index: number;
}

// ---- helpers for building config/answer_data per type ----

// imageId: the option's picture (T8); kept on the option so it moves with it.
interface McOption { text: string; points: number; imageId?: string | null }

/** `option_image_ids` only when at least one option has a picture (T8 §E). */
function optionImageConfig(options: McOption[]) {
  return options.some((o) => o.imageId) ? { option_image_ids: options.map((o) => o.imageId ?? null) } : {};
}

function buildMcPayload(options: McOption[], _grading: GradingType) {
  return {
    config: { options: options.map((o) => o.text), ...optionImageConfig(options) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

function buildTfPayload(truePoints: number, falsePoints: number) {
  return {
    config: {},
    answer_data: { answer_points: { true: truePoints, false: falsePoints } },
  };
}

function buildMsPayload(options: McOption[]) {
  return {
    config: { options: options.map((o) => o.text), ...optionImageConfig(options) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

interface FibAnswer { text: string; points: number }

function buildFibPayload(answers: FibAnswer[], editDistance: number) {
  return {
    config: {},
    answer_data: {
      acceptedAnswers: answers.map((a) => a.text),
      answerPoints: answers.map((a) => a.points),
      editDistance,
    },
  };
}

// numeric_estimate: a guess scored by tolerance bands around a hidden target.
// Band fields are kept as the text typed so a half-typed number is not forced to 0.
interface NeBand { within: string; points: string }
type NeMode = 'relative' | 'absolute';

const NE_MAX_BANDS = 5;
const NE_LIMIT = 1e15;
const NE_DEFAULT_TIME = 45; // typing a number takes longer than tapping an option

const neDefaultBands = (): NeBand[] => [
  { within: '5', points: '100' },
  { within: '15', points: '50' },
  { within: '30', points: '25' },
];

/** Plain-language problems with a numeric question, mirroring the backend's rules (the
 * server stays the authority). Empty when the form is fine. */
function numericProblems(form: FormState): string[] {
  const problems: string[] = [];
  if (form.neUnit.length > 20) problems.push('The unit can be at most 20 characters.');
  if (form.grading !== 'ACCURACY') return problems;
  const target = Number(form.neTarget);
  if (form.neTarget.trim() === '' || !Number.isFinite(target) || Math.abs(target) > NE_LIMIT) {
    problems.push('Enter the target number (at most 1e15 in size).');
  } else if (form.neMode === 'relative' && target === 0) {
    problems.push('A percentage of 0 is undefined: use Absolute mode or a non-zero target.');
  }
  const bands = form.neBands.map((b) => ({ within: Number(b.within), points: Number(b.points) }));
  if (bands.length < 1 || bands.length > NE_MAX_BANDS) {
    problems.push(`Use between 1 and ${NE_MAX_BANDS} bands.`);
  }
  if (bands.some((b, i) => form.neBands[i].within.trim() === '' || form.neBands[i].points.trim() === ''
      || !(b.within > 0) || !(b.points > 0) || b.within > NE_LIMIT || b.points > NE_LIMIT)) {
    problems.push('Every band needs a "within" and a points value greater than 0.');
  } else {
    if (bands.some((b, i) => i > 0 && b.within <= bands[i - 1].within)) {
      problems.push('Each band must be wider than the one before it ("within" increases).');
    }
    if (bands.some((b, i) => i > 0 && b.points >= bands[i - 1].points)) {
      problems.push('Each band must be worth fewer points than the one before it.');
    }
  }
  return problems;
}

function buildNePayload(form: FormState) {
  const unit = form.neUnit.trim();
  const config: Record<string, unknown> = unit ? { unit } : {};
  if (form.grading !== 'ACCURACY') return { config, answer_data: {} };
  return {
    config,
    answer_data: {
      target: Number(form.neTarget),
      mode: form.neMode,
      bands: form.neBands.map((b) => ({ within: Number(b.within), points: Number(b.points) })),
    },
  };
}

// ---- QuestionForm subcomponent ----

// plot_point fields (pp…) and their rules live in PlotPointEditor.tsx.
interface FormState extends PpForm {
  type: QuestionType;
  grading: GradingType;
  prompt: string;
  imageId: string | null; // prompt image (T8), any type
  timeLimitSeconds: number;
  pointsValue: number;
  // multiple_choice
  mcOptions: McOption[];
  // true_false
  tfTruePoints: number;
  tfFalsePoints: number;
  // fill_in_the_blank
  fibAnswers: FibAnswer[];
  fibEditDistance: number;
  // multi_select
  msOptions: McOption[];
  // numeric_estimate
  neTarget: string;
  neMode: NeMode;
  neUnit: string;
  neBands: NeBand[];
}

const defaultForm = (): FormState => ({
  type: 'multiple_choice',
  grading: 'ACCURACY',
  prompt: '',
  imageId: null,
  timeLimitSeconds: 30,
  pointsValue: 1,
  mcOptions: [{ text: '', points: 1 }, { text: '', points: 0 }],
  tfTruePoints: 1,
  tfFalsePoints: 0,
  fibAnswers: [{ text: '', points: 1 }],
  fibEditDistance: 0,
  msOptions: [{ text: '', points: 1 }, { text: '', points: 1 }],
  neTarget: '',
  neMode: 'relative',
  neUnit: '',
  neBands: neDefaultBands(),
  ...ppDefaultForm(),
});

function questionToForm(q: Question): FormState {
  const base: FormState = {
    ...defaultForm(),
    type: q.type,
    grading: q.grading_type,
    prompt: q.prompt,
    imageId: typeof q.config['image_id'] === 'string' ? q.config['image_id'] : null,
    timeLimitSeconds: q.time_limit_seconds,
    pointsValue: q.points_value,
  };
  const optionImages = Array.isArray(q.config['option_image_ids'])
    ? (q.config['option_image_ids'] as unknown[])
    : [];
  const optionImage = (i: number) => (typeof optionImages[i] === 'string' ? (optionImages[i] as string) : null);
  if (q.type === 'multiple_choice') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.mcOptions = opts.map((text, i) => ({ text, points: pts[i] ?? 0, imageId: optionImage(i) }));
  } else if (q.type === 'true_false') {
    const ap = q.answer_data['answer_points'] as { true: number; false: number } | undefined;
    base.tfTruePoints = ap?.true ?? 1;
    base.tfFalsePoints = ap?.false ?? 0;
  } else if (q.type === 'fill_in_the_blank') {
    const accepted = (q.answer_data['acceptedAnswers'] as string[]) ?? [];
    const pts = (q.answer_data['answerPoints'] as number[]) ?? [];
    base.fibAnswers = accepted.length
      ? accepted.map((text, i) => ({ text, points: pts[i] ?? 1 }))
      : [{ text: '', points: 1 }];
    base.fibEditDistance = (q.answer_data['editDistance'] as number) ?? 0;
  } else if (q.type === 'multi_select') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.msOptions = opts.length
      ? opts.map((text, i) => ({ text, points: pts[i] ?? 1, imageId: optionImage(i) }))
      : [{ text: '', points: 1 }, { text: '', points: 1 }];
  } else if (q.type === 'numeric_estimate') {
    const bands = (q.answer_data['bands'] as { within: number; points: number }[]) ?? [];
    base.neTarget = q.answer_data['target'] === undefined ? '' : String(q.answer_data['target']);
    base.neMode = (q.answer_data['mode'] as NeMode) === 'absolute' ? 'absolute' : 'relative';
    base.neUnit = (q.config['unit'] as string) ?? '';
    base.neBands = bands.length
      ? bands.map((b) => ({ within: String(b.within), points: String(b.points) }))
      : neDefaultBands();
  } else if (q.type === 'plot_point') {
    Object.assign(base, ppFromQuestion(q.config, q.answer_data));
  }
  return base;
}

function formToPayload(form: FormState) {
  let config: Record<string, unknown> = {};
  let answer_data: Record<string, unknown> = {};
  if (form.type === 'multiple_choice') {
    const p = buildMcPayload(form.mcOptions, form.grading);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'true_false') {
    const p = buildTfPayload(form.tfTruePoints, form.tfFalsePoints);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'multi_select') {
    const p = buildMsPayload(form.msOptions.filter((o) => o.text.trim()));
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'numeric_estimate') {
    const p = buildNePayload(form);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'plot_point') {
    const p = buildPpPayload(form, form.grading === 'ACCURACY');
    config = p.config;
    answer_data = p.answer_data;
  } else {
    const p = buildFibPayload(form.fibAnswers.filter((a) => a.text.trim()), form.fibEditDistance);
    config = p.config;
    answer_data = p.answer_data;
  }
  if (form.imageId) config = { ...config, image_id: form.imageId };
  const points_value =
    form.grading === 'COMPLETENESS'
      ? form.pointsValue
      : form.type === 'multiple_choice'
      ? Math.max(0, ...form.mcOptions.map((o) => o.points))
      : form.type === 'true_false'
      ? Math.max(form.tfTruePoints, form.tfFalsePoints)
      : form.type === 'multi_select'
      ? form.msOptions.reduce((sum, o) => sum + (o.points > 0 ? o.points : 0), 0)
      : form.type === 'numeric_estimate'
      ? Number(form.neBands[0]?.points ?? 0) // the first (best) band
      : form.type === 'plot_point'
      ? ppPointsValue(form)
      : Math.max(0, ...form.fibAnswers.map((a) => a.points));
  return {
    type: form.type,
    grading_type: form.grading,
    prompt: form.prompt,
    config,
    answer_data,
    time_limit_seconds: form.timeLimitSeconds,
    points_value,
  };
}

