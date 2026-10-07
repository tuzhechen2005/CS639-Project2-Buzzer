/**
 * The image library of one game and the image pickers of the question form (T8,
 * docs/plans/t8-image-support.md §H). Images belong to the game; questions reference
 * them by id in `config.image_id` and `config.option_image_ids`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ImagePlus, RefreshCw, Trash2, Upload, X } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { QuestionImage } from '../../components/ui/QuestionImage';

export interface LibraryImage {
  id: string;
  game_id: number;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  sha256: string;
  created_at: string;
  updated_at: string;
  used_by: number[]; // question ids
}

const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const ACCEPT = 'image/png,image/jpeg,image/webp';

function tooLarge(file: File): string | null {
  return file.size > MAX_UPLOAD_BYTES
    ? `${file.name} is ${(file.size / 1024 / 1024).toFixed(1)} MB; images can be at most 2 MB`
    : null;
}

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function fileForm(file: File): FormData {
  const form = new FormData();
  form.append('file', file);
  return form;
}

/** Library state for one game. `upload` returns the stored image: a file the game
 * already holds returns the existing image (the server answers 200, not 201). */
export function useImageLibrary(gameId: string | undefined) {
  const [images, setImages] = useState<LibraryImage[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!gameId) return;
    try {
      setImages(await api.get<LibraryImage[]>(`/games/${gameId}/images`));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load images');
    }
  }, [gameId]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError('');
    try {
      const result = await action();
      await refresh();
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Image request failed');
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File): Promise<LibraryImage | null> {
    const problem = tooLarge(file);
    if (problem) { setError(problem); return null; }
    return run(() => api.postForm<LibraryImage>(`/games/${gameId}/images`, fileForm(file)));
  }

  async function replace(id: string, file: File): Promise<void> {
    const problem = tooLarge(file);
    if (problem) { setError(problem); return; }
    await run(() => api.putForm(`/games/${gameId}/images/${id}`, fileForm(file)));
  }

  async function remove(id: string): Promise<void> {
    await run(() => api.delete(`/games/${gameId}/images/${id}`));
  }

  const byId = (id: string | null | undefined) => images.find((img) => img.id === id);

  return { images, error, busy, refresh, upload, replace, remove, byId, clearError: () => setError('') };
}

export type ImageLibraryState = ReturnType<typeof useImageLibrary>;

/** A hidden file input opened by a button; calls `onFile` with the chosen file. */
function FileButton({
  label, icon, onFile, disabled, size = 'sm', variant = 'outline',
}: {
  label: string;
  icon: React.ReactNode;
  onFile: (file: File) => void;
  disabled?: boolean;
  size?: 'sm' | 'md';
  variant?: 'outline' | 'ghost';
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ''; // the same file can be picked again
          if (file) onFile(file);
        }}
      />
      <Button type="button" variant={variant} size={size} disabled={disabled} onClick={() => input.current?.click()}>
        {icon}
        {label}
      </Button>
    </>
  );
}

export function ImageLibraryPanel({
  library, questionNumbers, locked,
}: {
  library: ImageLibraryState;
  /** question id → its number as the editor shows it (Q1, Q2, …) */
  questionNumbers: Map<number, number>;
  locked: boolean;
}) {
  const { images, error, busy } = library;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-fg">Image library</h3>
            <p className="text-fg-subtle text-xs mt-0.5">
              PNG, JPEG or WebP, up to 2 MB each. Large photos are scaled down to 1600 px.
            </p>
          </div>
          {!locked && (
            <FileButton
              label={busy ? 'Working…' : 'Upload image'}
              icon={<Upload size={14} className="mr-1" />}
              disabled={busy}
              onFile={(file) => void library.upload(file)}
            />
          )}
        </div>
      </CardHeader>
      <CardContent>
        {locked && (
          <p className="text-warning-text text-xs mb-3">
            This game has been played, so its images can't be changed. Duplicate it to edit them.
          </p>
        )}
        {error && <p className="text-danger-text text-sm mb-3">{error}</p>}
        {images.length === 0 ? (
          <p className="text-fg-subtle text-sm">No images yet.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {images.map((img) => {
              const used = img.used_by
                .map((qid) => questionNumbers.get(qid))
                .filter((n): n is number => n !== undefined)
                .sort((a, b) => a - b);
              return (
                <div key={img.id} className="rounded-lg border border-line bg-surface p-2 space-y-2">
                  <a className="focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page" href={`/api/images/${img.id}?v=${img.sha256}`} target="_blank" rel="noreferrer" title="Open full size">
                    <QuestionImage
                      imageId={img.id}
                      version={img.sha256}
                      alt="Library image"
                      className="h-24 w-full bg-surface-raised rounded-lg"
                    />
                  </a>
                  <p className="text-xs text-fg-muted">
                    {img.width}×{img.height} · {formatSize(img.size_bytes)}
                  </p>
                  <p className={`text-xs ${used.length ? 'text-accent-text' : 'text-fg-subtle'}`}>
                    {used.length ? `Used by ${used.map((n) => `Q${n}`).join(', ')}` : 'Unused'}
                  </p>
                  {!locked && (
                    <div className="flex gap-1">
                      <FileButton
                        label="Replace"
                        icon={<RefreshCw size={12} className="mr-1" />}
                        variant="ghost"
                        disabled={busy}
                        onFile={(file) => void library.replace(img.id, file)}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        title="Delete image"
                        onClick={() => void library.remove(img.id)}
                      >
                        <Trash2 size={12} />
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Choose an image for a prompt or an option: pick one from the library, upload a new
 * one, or clear the choice. `value` is an image id or null.
 */
export function ImagePicker({
  library, value, onChange, label,
}: {
  library: ImageLibraryState;
  value: string | null;
  onChange: (id: string | null) => void;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = library.byId(value);
  return (
    <div className="relative">
      <div className="flex items-center gap-1">
        {value ? (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            title={`${label}: change`}
            className="h-9 w-12 rounded border border-line bg-surface-raised overflow-hidden focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
          >
            {selected ? (
              <QuestionImage imageId={value} version={selected.sha256} alt={label} className="h-full w-full" fallbackText={null} />
            ) : (
              <span className="text-[10px] text-danger-text">missing</span>
            )}
          </button>
        ) : (
          <Button type="button" variant="ghost" size="sm" title={`${label}: choose`} onClick={() => setOpen(!open)}>
            <ImagePlus size={14} />
          </Button>
        )}
        {value && (
          <Button type="button" variant="ghost" size="sm" title={`${label}: remove`} onClick={() => onChange(null)}>
            <X size={12} />
          </Button>
        )}
      </div>
      {open && (
        <div className="absolute z-20 right-0 mt-1 w-72 rounded-xl border border-line bg-surface p-3 shadow-xl space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-fg-muted">{label}</span>
            <button type="button" className="text-fg-subtle hover:text-fg focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page" onClick={() => setOpen(false)}>
              <X size={14} />
            </button>
          </div>
          {library.images.length > 0 ? (
            <div className="grid grid-cols-3 gap-2 max-h-56 overflow-y-auto">
              {library.images.map((img) => (
                <button
                  key={img.id}
                  type="button"
                  onClick={() => { onChange(img.id); setOpen(false); }}
                  className={`focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page h-16 rounded border bg-surface-raised ${img.id === value ? 'border-accent' : 'border-line hover:border-line-strong'}`}
                >
                  <QuestionImage imageId={img.id} version={img.sha256} alt="Library image" className="h-full w-full" fallbackText={null} />
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-fg-subtle">The library is empty.</p>
          )}
          <FileButton
            label={library.busy ? 'Uploading…' : 'Upload new'}
            icon={<Upload size={12} className="mr-1" />}
            disabled={library.busy}
            onFile={async (file) => {
              const img = await library.upload(file);
              if (img) { onChange(img.id); setOpen(false); }
            }}
          />
          {library.error && <p className="text-xs text-danger-text">{library.error}</p>}
        </div>
      )}
    </div>
  );
}
