import { useEffect, useState } from 'react';
import { useMatch } from 'react-router-dom';
import { Moon, Sun } from 'lucide-react';
import { setTheme, type Theme } from '../theme/theme';

function appliedTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

/**
 * Light/dark switch (docs/plans/t9-theming.md, "Toggle"), rendered once in App.tsx and fixed in
 * the top-right corner below the safe-area inset. Hidden on the question screen, where every tap
 * should be an answer. Fixed name "Dark theme", state in aria-pressed; the icon shows the current
 * theme. It reads <html data-theme> and re-renders on every `themechange`, so it stays right when
 * the app follows an OS change.
 */
export function ThemeToggle() {
  const onQuestion = useMatch('/game/:code/question') !== null;
  const [theme, setShown] = useState<Theme>(appliedTheme);

  useEffect(() => {
    const sync = () => setShown(appliedTheme());
    sync(); // a change between the first render and this effect
    window.addEventListener('themechange', sync);
    return () => window.removeEventListener('themechange', sync);
  }, []);

  if (onQuestion) return null;
  const dark = theme === 'dark';
  return (
    <button
      type="button"
      aria-label="Dark theme"
      title="Dark theme"
      aria-pressed={dark}
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      className="fixed right-3 top-[max(0.75rem,env(safe-area-inset-top))] z-40 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-line-strong bg-surface text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
    >
      {dark ? <Moon size={20} aria-hidden /> : <Sun size={20} aria-hidden />}
    </button>
  );
}
