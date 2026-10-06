import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { cn } from '../lib/utils';
import { setTheme, type Theme } from '../theme/theme';

function appliedTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

/**
 * Light/dark switch (docs/plans/t9-theming.md, "Toggle"). Fixed name "Dark theme", state in
 * aria-pressed; the icon shows the current theme. It keeps no theme of its own: it reads
 * <html data-theme> and re-renders on every `themechange`, so it stays right when the app follows
 * an OS change. Callers place it with `className`.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setShown] = useState<Theme>(appliedTheme);

  useEffect(() => {
    const sync = () => setShown(appliedTheme());
    sync(); // a change between the first render and this effect
    window.addEventListener('themechange', sync);
    return () => window.removeEventListener('themechange', sync);
  }, []);

  const dark = theme === 'dark';
  return (
    <button
      type="button"
      aria-label="Dark theme"
      title="Dark theme"
      aria-pressed={dark}
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      className={cn(
        'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-line-strong bg-surface text-fg-muted transition-colors',
        'hover:bg-surface-raised hover:text-fg',
        'focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page',
        className
      )}
    >
      {dark ? <Moon size={18} aria-hidden /> : <Sun size={18} aria-hidden />}
    </button>
  );
}
