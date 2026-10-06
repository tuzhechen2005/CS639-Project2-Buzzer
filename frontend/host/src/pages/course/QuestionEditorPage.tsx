import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Trash2, ChevronUp, ChevronDown, Download, Copy, Lock, Pencil } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import type { Game } from './GamesTab';
import { ImageLibraryPanel, ImagePicker, useImageLibrary, type ImageLibraryState } from './ImageLibrary';
import { QuestionImage } from '../../components/ui/QuestionImage';
import { PromptText } from '../../components/PromptText';
import {
  PP_DEFAULT_TIME, PlotPointFields, buildPpPayload, plotProblems, ppDefaultForm, ppFromQuestion,
  ppListSummary, ppPointsValue, type PpForm,
} from './PlotPointEditor';

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

function QuestionForm({
  initial,
  onSave,
  onCancel,
  saving,
  library,
}: {
  library: ImageLibraryState;
  initial: FormState;
  onSave: (payload: ReturnType<typeof formToPayload>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<FormState>(initial);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="space-y-4">
      {/* Type + grading */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs text-fg-muted mb-1">Question type</label>
          <select
            className="w-full rounded-xl border border-line-strong bg-surface-raised px-3 py-2 text-fg text-sm focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
            value={form.type}
            onChange={(e) => {
              const type = e.target.value as QuestionType;
              setForm((prev) => ({
                ...prev,
                type,
                // typing a number takes longer than tapping: raise the untouched default
                timeLimitSeconds:
                  type === 'numeric_estimate' && prev.timeLimitSeconds === 30
                    ? NE_DEFAULT_TIME
                    : type === 'plot_point' && prev.timeLimitSeconds === 30
                    ? PP_DEFAULT_TIME
                    : prev.timeLimitSeconds,
              }));
            }}
          >
            <option value="multiple_choice">Multiple Choice</option>
            <option value="true_false">True / False</option>
            <option value="fill_in_the_blank">Fill in the Blank</option>
            <option value="multi_select">Multi-Select (Select All That Apply)</option>
            <option value="numeric_estimate">Numeric Estimate (closest guess)</option>
            <option value="plot_point">Plot the Point (tap a coordinate plane)</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs text-fg-muted mb-1">Grading</label>
          <select
            className="w-full rounded-xl border border-line-strong bg-surface-raised px-3 py-2 text-fg text-sm focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
            value={form.grading}
            onChange={(e) => set('grading', e.target.value as GradingType)}
          >
            <option value="ACCURACY">Accuracy</option>
            <option value="COMPLETENESS">Completeness</option>
          </select>
        </div>
      </div>

      {/* Prompt */}
      <div>
        <label className="block text-xs text-fg-muted mb-1">Prompt</label>
        <textarea
          className="w-full rounded-xl border border-line-strong bg-surface-raised px-3 py-2 text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page resize-none text-sm"
          rows={3}
          placeholder="Question text…"
          value={form.prompt}
          onChange={(e) => set('prompt', e.target.value)}
          required
        />
        <div className="flex items-center gap-2 mt-2">
          {/* plot_point: the same config.image_id is the plane's background (Decision 9). */}
          <span className="text-xs text-fg-muted">
            {form.type === 'plot_point' ? 'Background image (optional)' : 'Prompt image (optional)'}
          </span>
          <ImagePicker
            library={library}
            value={form.imageId}
            onChange={(id) => set('imageId', id)}
            label={form.type === 'plot_point' ? 'Background image' : 'Prompt image'}
          />
        </div>
      </div>

      {/* Type-specific */}
      {form.type === 'multiple_choice' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-fg-subtle">Answer text</span>
              <span className="w-24 text-xs text-fg-subtle">Points</span>
              {form.mcOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.mcOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.mcOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('mcOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                <ImagePicker
                  library={library}
                  value={opt.imageId ?? null}
                  onChange={(id) => {
                    const opts = [...form.mcOptions];
                    opts[i] = { ...opts[i], imageId: id };
                    set('mcOptions', opts);
                  }}
                  label={`Image for option ${i + 1}`}
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.mcOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('mcOptions', opts);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                )}
                {form.mcOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('mcOptions', form.mcOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('mcOptions', [...form.mcOptions, { text: '', points: 0 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
        </div>
      )}

      {form.type === 'multi_select' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-fg-subtle">Answer text</span>
              <span className="w-24 text-xs text-fg-subtle">Points (neg = penalty)</span>
              {form.msOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.msOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.msOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('msOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                <ImagePicker
                  library={library}
                  value={opt.imageId ?? null}
                  onChange={(id) => {
                    const opts = [...form.msOptions];
                    opts[i] = { ...opts[i], imageId: id };
                    set('msOptions', opts);
                  }}
                  label={`Image for option ${i + 1}`}
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.msOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('msOptions', opts);
                    }}
                    className="w-24 text-sm"
                    step="any"
                  />
                )}
                {form.msOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('msOptions', form.msOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('msOptions', [...form.msOptions, { text: '', points: 1 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
          {form.grading === 'ACCURACY' && (
            <p className="text-fg-subtle text-xs mt-1">
              Correct options: positive pts. Distractors: negative pts (penalty). Score = sum of selected, capped at 0.
            </p>
          )}
        </div>
      )}

      {form.type === 'true_false' && form.grading === 'ACCURACY' && (
        <div>
          <label className="block text-xs text-fg-muted mb-2">Points per answer</label>
          <div className="flex gap-4">
            <div>
              <span className="text-fg-muted text-sm">True:</span>
              <Input
                type="number"
                value={form.tfTruePoints}
                onChange={(e) => set('tfTruePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
            <div>
              <span className="text-fg-muted text-sm">False:</span>
              <Input
                type="number"
                value={form.tfFalsePoints}
                onChange={(e) => set('tfFalsePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
          </div>
        </div>
      )}

      {form.type === 'fill_in_the_blank' && form.grading === 'ACCURACY' && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-fg-muted mb-2">Accepted answers</label>
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-fg-subtle">Answer text</span>
              <span className="w-24 text-xs text-fg-subtle">Points</span>
              {form.fibAnswers.length > 1 && <span className="w-7" />}
            </div>
            <div className="space-y-2">
              {form.fibAnswers.map((ans, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <Input
                    placeholder={`Answer ${i + 1}`}
                    value={ans.text}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], text: e.target.value };
                      set('fibAnswers', answers);
                    }}
                    className="flex-1 text-sm"
                  />
                  <Input
                    type="number"
                    placeholder="pts"
                    value={ans.points}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], points: Number(e.target.value) };
                      set('fibAnswers', answers);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                  {form.fibAnswers.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => set('fibAnswers', form.fibAnswers.filter((_, j) => j !== i))}
                    >
                      <Trash2 size={12} />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => set('fibAnswers', [...form.fibAnswers, { text: '', points: 1 }])}
              >
                <Plus size={12} className="mr-1" /> Add answer
              </Button>
            </div>
          </div>
          <div>
            <label className="block text-xs text-fg-muted mb-1">Edit distance tolerance (fuzzy match)</label>
            <Input
              type="number"
              value={form.fibEditDistance}
              onChange={(e) => set('fibEditDistance', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
            />
          </div>
        </div>
      )}

      {form.type === 'numeric_estimate' && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3">
            {form.grading === 'ACCURACY' && (
              <>
                <div>
                  <label className="block text-xs text-fg-muted mb-1">Target (the true value)</label>
                  <Input
                    type="number"
                    step="any"
                    placeholder="e.g. 1665"
                    value={form.neTarget}
                    onChange={(e) => set('neTarget', e.target.value)}
                    className="w-40 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-fg-muted mb-1">Tolerance is measured in</label>
                  <select
                    className="rounded-xl border border-line-strong bg-surface-raised px-3 py-2 text-fg text-sm focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                    value={form.neMode}
                    onChange={(e) => set('neMode', e.target.value as NeMode)}
                  >
                    <option value="relative">Percent of the target</option>
                    <option value="absolute">The answer's own units</option>
                  </select>
                </div>
              </>
            )}
            <div>
              <label className="block text-xs text-fg-muted mb-1">Unit (optional)</label>
              <Input
                placeholder="steps, years, m…"
                maxLength={20}
                value={form.neUnit}
                onChange={(e) => set('neUnit', e.target.value)}
                className="w-36 text-sm"
              />
            </div>
          </div>

          {form.grading === 'ACCURACY' && (
            <div>
              <label className="block text-xs text-fg-muted mb-2">
                Bands: a guess within the tolerance earns the points (the first band that fits wins)
              </label>
              <div className="flex gap-2 mb-1 px-0.5">
                <span className="w-32 text-xs text-fg-subtle">
                  Within {form.neMode === 'relative' ? '(%)' : form.neUnit ? `(${form.neUnit})` : '(units)'}
                </span>
                <span className="w-24 text-xs text-fg-subtle">Points</span>
                {form.neBands.length > 1 && <span className="w-7" />}
              </div>
              <div className="space-y-2">
                {form.neBands.map((band, i) => (
                  <div key={i} className="flex gap-2 items-center">
                    <Input
                      type="number"
                      step="any"
                      min="0"
                      value={band.within}
                      onChange={(e) => {
                        const bands = [...form.neBands];
                        bands[i] = { ...bands[i], within: e.target.value };
                        set('neBands', bands);
                      }}
                      className="w-32 text-sm"
                    />
                    <Input
                      type="number"
                      step="any"
                      min="0"
                      value={band.points}
                      onChange={(e) => {
                        const bands = [...form.neBands];
                        bands[i] = { ...bands[i], points: e.target.value };
                        set('neBands', bands);
                      }}
                      className="w-24 text-sm"
                    />
                    {i === 0 && <span className="text-xs text-success-text">best band = correct</span>}
                    {form.neBands.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => set('neBands', form.neBands.filter((_, j) => j !== i))}
                      >
                        <Trash2 size={12} />
                      </Button>
                    )}
                  </div>
                ))}
                {form.neBands.length < NE_MAX_BANDS && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const last = form.neBands[form.neBands.length - 1];
                      const within = last ? String(Number(last.within) * 2 || '') : '';
                      const points = last ? String(Math.max(1, Math.floor(Number(last.points) / 2)) || '') : '';
                      set('neBands', [...form.neBands, { within, points }]);
                    }}
                  >
                    <Plus size={12} className="mr-1" /> Add band
                  </Button>
                )}
              </div>
              <p className="text-xs text-fg-subtle mt-2">
                Question points (the best band): {form.neBands[0]?.points || '—'}
              </p>
            </div>
          )}

          {numericProblems(form).length > 0 && (
            <ul className="text-xs text-warning-text list-disc pl-5 space-y-0.5">
              {numericProblems(form).map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
        </div>
      )}

      {form.type === 'plot_point' && (
        <PlotPointFields
          form={form}
          accuracy={form.grading === 'ACCURACY'}
          imageId={form.imageId}
          onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
        />
      )}

      {/* Time + points */}
      <div className="flex gap-4">
        <div>
          <label className="block text-xs text-fg-muted mb-1">Time limit (seconds)</label>
          <Input
            type="number"
            value={form.timeLimitSeconds}
            onChange={(e) => set('timeLimitSeconds', Number(e.target.value))}
            className="w-28 text-sm"
            min="2"
            max="300"
          />
        </div>
        {form.grading === 'COMPLETENESS' && (
          <div>
            <label className="block text-xs text-fg-muted mb-1">Points value</label>
            <Input
              type="number"
              value={form.pointsValue}
              onChange={(e) => set('pointsValue', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
              max="100000"
              step="any"
            />
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <Button
          type="button"
          onClick={() => onSave(formToPayload(form))}
          disabled={
            saving
            || (form.type === 'numeric_estimate' && numericProblems(form).length > 0)
            || (form.type === 'plot_point' && plotProblems(form, form.grading === 'ACCURACY').length > 0)
          }
        >
          {saving ? 'Saving…' : 'Save Question'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

// ---- Main page ----

/**
 * A game's questions, under its course (`/courses/:courseId/games/:gameId/questions`).
 * Locked games (with recorded answers) are read-only apart from the title, description
 * and max players; Duplicate makes an editable copy.
 */
export default function QuestionEditorPage() {
  const { courseId, gameId } = useParams<{ courseId: string; gameId: string }>();
  const navigate = useNavigate();
  const [game, setGame] = useState<Game | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  // Game details header
  const [editingDetails, setEditingDetails] = useState(false);
  const [detailTitle, setDetailTitle] = useState('');
  const [detailDescription, setDetailDescription] = useState('');
  const [detailMaxPlayers, setDetailMaxPlayers] = useState('');
  const [detailSaving, setDetailSaving] = useState(false);
  const library = useImageLibrary(gameId);

  async function load() {
    let redirected = false;
    try {
      const [g, qs] = await Promise.all([
        api.get<Game>(`/games/${gameId}`),
        api.get<Question[]>(`/games/${gameId}/questions`),
      ]);
      if (String(g.course_id) !== courseId) {
        // The game belongs to another course: show it under the right one. Keep the
        // spinner up until the new route loads, so "Game not found" doesn't flash.
        redirected = true;
        navigate(`/courses/${g.course_id}/games/${g.id}/questions`, { replace: true });
        return;
      }
      setGame(g);
      setQuestions(qs);
      void library.refresh(); // "Used by" changes with every question save
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      if (!redirected) setLoading(false);
    }
  }

  useEffect(() => {
    // The page stays mounted when only gameId changes (Duplicate opens the copy in the same
    // course), so drop the previous game: a failed load must not leave it on screen while
    // edits post to the new id.
    setGame(null);
    setQuestions([]);
    setError('');
    setLoading(true);
    setShowAddForm(false);
    setEditingId(null);
    setEditingDetails(false);
    void load();
  }, [courseId, gameId]);

  function startEditDetails(g: Game) {
    setDetailTitle(g.title);
    setDetailDescription(g.description);
    setDetailMaxPlayers(String(g.max_players));
    setEditingDetails(true);
  }

  async function saveDetails(e: React.FormEvent) {
    e.preventDefault();
    setDetailSaving(true);
    setError('');
    try {
      const updated = await api.put<Game>(`/games/${gameId}`, {
        title: detailTitle,
        description: detailDescription,
        max_players: Number(detailMaxPlayers),
      });
      setGame(updated);
      setEditingDetails(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save game details');
    } finally {
      setDetailSaving(false);
    }
  }

  async function addQuestion(payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.post(`/games/${gameId}/questions`, payload);
      setShowAddForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save question');
      // The game may have been played or opened in a room meanwhile (409); reload so
      // the page shows its current state.
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function updateQuestion(id: number, payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.put(`/games/${gameId}/questions/${id}`, payload);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update question');
      await load();
    } finally {
      setSaving(false);
    }
  }

  async function deleteQuestion(id: number) {
    if (!confirm('Delete this question?')) return;
    setError('');
    try {
      await api.delete(`/games/${gameId}/questions/${id}`);
      setQuestions((prev) => prev.filter((q) => q.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete question');
      await load();
    }
  }

  async function moveQuestion(index: number, direction: -1 | 1) {
    const newOrder = [...questions];
    const target = index + direction;
    if (target < 0 || target >= newOrder.length) return;
    [newOrder[index], newOrder[target]] = [newOrder[target], newOrder[index]];
    setError('');
    try {
      await api.post(`/games/${gameId}/questions/reorder`, {
        order: newOrder.map((q) => q.id),
      });
      setQuestions(newOrder);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder');
      // A co-host may have changed the questions; show the current list.
      await load();
    }
  }

  async function handleExport() {
    setDownloading(true);
    setError('');
    try {
      await api.download(`/games/${gameId}/export`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setDownloading(false);
    }
  }

  async function handleDuplicate() {
    setDuplicating(true);
    setError('');
    try {
      const copy = await api.post<Game>(`/games/${gameId}/duplicate`);
      navigate(`/courses/${copy.course_id}/games/${copy.id}/questions`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to duplicate game');
    } finally {
      setDuplicating(false);
    }
  }

  const typeLabel: Record<QuestionType, string> = {
    multiple_choice: 'MC',
    true_false: 'T/F',
    fill_in_the_blank: 'Fill',
    multi_select: 'Multi',
    numeric_estimate: 'Num',
    plot_point: 'Plot',
  };

  if (loading) return <div className="text-fg-muted">Loading…</div>;
  if (!game) return <p className="text-danger-text text-sm">{error || 'Game not found.'}</p>;

  const locked = game.locked;

  return (
    <div className="max-w-4xl space-y-6">
      {/* Game details */}
      <Card>
        {editingDetails ? (
          <>
            <CardHeader><h3 className="text-lg font-semibold text-fg">Game details</h3></CardHeader>
            <CardContent>
              <form onSubmit={saveDetails} className="space-y-3">
                <Input placeholder="Title" value={detailTitle} onChange={(e) => setDetailTitle(e.target.value)} required />
                <textarea
                  placeholder="Description (optional)"
                  value={detailDescription}
                  onChange={(e) => setDetailDescription(e.target.value)}
                  className="w-full rounded-xl border border-line-strong bg-surface-raised px-3 py-2 text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page resize-none"
                  rows={3}
                />
                <div>
                  <label className="block text-xs text-fg-muted mb-1">Max players</label>
                  <Input
                    type="number"
                    value={detailMaxPlayers}
                    onChange={(e) => setDetailMaxPlayers(e.target.value)}
                    min="1"
                    max="500"
                    className="w-32"
                  />
                </div>
                <div className="flex gap-3">
                  <Button type="submit" disabled={detailSaving}>{detailSaving ? 'Saving…' : 'Save'}</Button>
                  <Button type="button" variant="ghost" onClick={() => setEditingDetails(false)}>Cancel</Button>
                </div>
              </form>
            </CardContent>
          </>
        ) : (
          <div className="flex items-start justify-between gap-4 px-6 py-4">
            <div className="min-w-0">
              <h2 className="text-2xl font-bold text-fg">{game.title}</h2>
              {game.description && <p className="text-fg-muted text-sm mt-1">{game.description}</p>}
              <p className="text-fg-subtle text-xs mt-1">
                {questions.length} question{questions.length !== 1 ? 's' : ''} · Max {game.max_players} players
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button variant="outline" size="sm" onClick={() => startEditDetails(game)}>
                <Pencil size={14} className="mr-1" /> Edit details
              </Button>
              <Button variant="outline" size="sm" onClick={() => void handleExport()} disabled={downloading}>
                <Download size={14} className="mr-1" />
                {downloading ? 'Exporting…' : 'Export JSON'}
              </Button>
              {locked ? (
                <Button size="sm" onClick={() => void handleDuplicate()} disabled={duplicating}>
                  <Copy size={14} className="mr-1" /> {duplicating ? 'Duplicating…' : 'Duplicate to edit'}
                </Button>
              ) : (
                <Button size="sm" onClick={() => { setShowAddForm(true); setEditingId(null); }}>
                  <Plus size={14} className="mr-1" /> Add Question
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>

      {locked && (
        <div className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning-subtle px-4 py-3 text-sm text-warning-text">
          <Lock size={16} className="mt-0.5 shrink-0" />
          <p>
            This game has been played and has recorded answers, so its questions can't be changed
            (past scores and reports depend on them). Use <strong>Duplicate to edit</strong> to make an
            editable copy. The title, description and max players can still be edited.
          </p>
        </div>
      )}

      {error && <p className="text-danger-text text-sm">{error}</p>}

      <ImageLibraryPanel
        library={library}
        questionNumbers={new Map(questions.map((q, i) => [q.id, i + 1]))}
        locked={locked}
      />

      {/* Add question form */}
      {showAddForm && !locked && (
        <Card>
          <CardHeader><h3 className="font-semibold text-fg">New Question</h3></CardHeader>
          <CardContent>
            <QuestionForm
              initial={defaultForm()}
              library={library}
              onSave={(payload) => void addQuestion(payload)}
              onCancel={() => setShowAddForm(false)}
              saving={saving}
            />
          </CardContent>
        </Card>
      )}

      {/* Question list */}
      {questions.length === 0 && !showAddForm && (
        <p className="text-fg-muted">No questions yet. Add one above.</p>
      )}

      <div className="space-y-4">
        {questions.map((q, i) => (
          <Card key={q.id}>
            {editingId === q.id && !locked ? (
              <>
                <CardHeader>
                  <h3 className="font-semibold text-fg">Edit Question {i + 1}</h3>
                </CardHeader>
                <CardContent>
                  <QuestionForm
                    initial={questionToForm(q)}
                    library={library}
                    onSave={(payload) => void updateQuestion(q.id, payload)}
                    onCancel={() => setEditingId(null)}
                    saving={saving}
                  />
                </CardContent>
              </>
            ) : (
              <div className="flex items-start gap-4 px-6 py-4">
                {/* Reorder buttons */}
                {!locked && (
                  <div className="flex flex-col gap-1 mt-1">
                    <button
                      onClick={() => void moveQuestion(i, -1)}
                      disabled={i === 0}
                      className="text-fg-subtle hover:text-fg disabled:opacity-20 focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                      title="Move up"
                    >
                      <ChevronUp size={16} />
                    </button>
                    <button
                      onClick={() => void moveQuestion(i, 1)}
                      disabled={i === questions.length - 1}
                      className="text-fg-subtle hover:text-fg disabled:opacity-20 focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                      title="Move down"
                    >
                      <ChevronDown size={16} />
                    </button>
                  </div>
                )}

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-fg-subtle text-xs font-mono">Q{i + 1}</span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-surface-raised text-fg-muted">
                      {typeLabel[q.type]}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-surface-raised text-fg-muted">
                      {q.grading_type}
                    </span>
                    <span className="text-fg-subtle text-xs">{q.time_limit_seconds}s · {q.points_value}pts</span>
                  </div>
                  <p className="text-fg text-sm leading-relaxed"><PromptText prompt={q.prompt} /></p>
                  {typeof q.config['image_id'] === 'string' && (
                    <QuestionImage
                      imageId={q.config['image_id']}
                      version={library.byId(q.config['image_id'])?.sha256}
                      alt={q.type === 'plot_point' ? 'Background image' : 'Prompt image'}
                      className="h-16 w-28 mt-2"
                      align="left"
                    />
                  )}

                  {q.type === 'multiple_choice' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={pts > 0 ? 'text-success-text' : 'text-fg-subtle'}>
                              {pts > 0 ? '✓' : '○'}
                            </span>
                            {typeof (q.config['option_image_ids'] as unknown[] | undefined)?.[oi] === 'string' && (
                              <QuestionImage
                                imageId={(q.config['option_image_ids'] as string[])[oi]}
                                version={library.byId((q.config['option_image_ids'] as string[])[oi])?.sha256}
                                alt={opt}
                                className="h-6 w-9"
                                fallbackText={null}
                              />
                            )}
                            <span className={pts > 0 ? 'text-fg' : 'text-fg-muted'}>{opt}</span>
                            {pts > 0 && <span className="text-fg-subtle">({pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'true_false' && (
                    <div className="mt-2 flex gap-4 text-xs">
                      {(['true', 'false'] as const).map((k) => {
                        const pts = (q.answer_data['answer_points'] as Record<string, number>)?.[k] ?? 0;
                        return (
                          <span key={k} className={pts > 0 ? 'text-success-text' : 'text-fg-subtle'}>
                            {k.charAt(0).toUpperCase() + k.slice(1)}: {pts}pts
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'fill_in_the_blank' && (
                    <div className="mt-2 text-xs text-fg-muted">
                      Accepted: {((q.answer_data['acceptedAnswers'] as string[]) ?? []).join(', ')}
                      {(q.answer_data['editDistance'] as number) > 0 && (
                        <span className="ml-2 text-fg-subtle">(±{q.answer_data['editDistance'] as number} edit distance)</span>
                      )}
                    </div>
                  )}

                  {q.type === 'numeric_estimate' && (
                    <div className="mt-2 text-xs text-fg-muted space-y-0.5">
                      {q.grading_type === 'ACCURACY' ? (
                        <>
                          <div>
                            Target: <span className="text-success-text">
                              {String(q.answer_data['target'])}{q.config['unit'] ? ` ${String(q.config['unit'])}` : ''}
                            </span>
                            <span className="ml-2 text-fg-subtle">
                              ({q.answer_data['mode'] === 'relative' ? 'percent of the target' : 'absolute units'})
                            </span>
                          </div>
                          <div>
                            {((q.answer_data['bands'] as { within: number; points: number }[]) ?? [])
                              .map((b) => `±${b.within}${q.answer_data['mode'] === 'relative' ? '%' : ''} → ${b.points}pts`)
                              .join(' · ')}
                          </div>
                        </>
                      ) : (
                        <div>Any number earns full points{q.config['unit'] ? ` (${String(q.config['unit'])})` : ''}</div>
                      )}
                    </div>
                  )}

                  {q.type === 'plot_point' && (
                    <div className="mt-2 text-xs text-fg-muted">
                      {ppListSummary(q.config, q.answer_data, q.grading_type === 'ACCURACY')}
                    </div>
                  )}

                  {q.type === 'multi_select' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        const isCorrect = pts > 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={isCorrect ? 'text-success-text' : pts < 0 ? 'text-danger-text' : 'text-fg-subtle'}>
                              {isCorrect ? '✓' : pts < 0 ? '−' : '○'}
                            </span>
                            {typeof (q.config['option_image_ids'] as unknown[] | undefined)?.[oi] === 'string' && (
                              <QuestionImage
                                imageId={(q.config['option_image_ids'] as string[])[oi]}
                                version={library.byId((q.config['option_image_ids'] as string[])[oi])?.sha256}
                                alt={opt}
                                className="h-6 w-9"
                                fallbackText={null}
                              />
                            )}
                            <span className={isCorrect ? 'text-fg' : 'text-fg-muted'}>{opt}</span>
                            {pts !== 0 && <span className="text-fg-subtle">({pts > 0 ? '+' : ''}{pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {!locked && (
                  <div className="flex gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setEditingId(q.id); setShowAddForm(false); }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void deleteQuestion(q.id)}
                      title="Delete question"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
