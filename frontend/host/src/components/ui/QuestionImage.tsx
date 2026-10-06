import { useEffect, useRef, useState } from 'react';
import { cn } from '../../lib/utils';
import { imageUrl } from '../../lib/images';

interface QuestionImageProps {
  /** Image id from a question's config; nothing is rendered when it is missing. */
  imageId?: string | null;
  alt: string;
  /** Size of the box. The placeholder takes the same size while the image loads. */
  className?: string;
  /** Shown instead of the image when it fails to load; null shows nothing. */
  fallbackText?: string | null;
  /** Where the picture sits inside a box wider than it: centred, or against the left edge. */
  align?: 'center' | 'left';
  /** The image's sha256 (editor only), so a replaced image is not served from cache. */
  version?: string;
}

/**
 * A question or option image (docs/plans/t8-image-support.md §H). While it loads, a
 * neutral placeholder of the same size is shown; if it fails, a short note (or nothing).
 * It never blocks the question: there is no pre-loading and the timer does not wait.
 */
export function QuestionImage({ imageId, ...rest }: QuestionImageProps) {
  if (!imageId) return null;
  // Keyed by id and version, so a new image starts again from the loading state.
  return <LoadedImage key={`${imageId}:${rest.version ?? ''}`} imageId={imageId} {...rest} />;
}

function LoadedImage({
  imageId,
  alt,
  className,
  fallbackText = 'Image could not be loaded',
  align = 'center',
  version,
}: QuestionImageProps & { imageId: string }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const ref = useRef<HTMLImageElement>(null);

  // A cached image may finish before React attaches onLoad.
  useEffect(() => {
    const img = ref.current;
    if (img?.complete) setStatus(img.naturalWidth > 0 ? 'loaded' : 'error');
  }, []);

  if (status === 'error') {
    return fallbackText ? <p className="text-slate-500 text-sm italic">{fallbackText}</p> : null;
  }
  return (
    <span className={cn('relative block', className)}>
      {status === 'loading' && (
        <span aria-hidden className="absolute inset-0 rounded-lg bg-slate-700/60 animate-pulse" />
      )}
      <img
        ref={ref}
        src={imageUrl(imageId, version)}
        alt={alt}
        onLoad={() => setStatus('loaded')}
        onError={() => setStatus('error')}
        className={cn(
          'h-full w-full object-contain rounded-lg transition-opacity',
          align === 'left' && 'object-left',
          status === 'loaded' ? 'opacity-100' : 'opacity-0',
        )}
      />
    </span>
  );
}
