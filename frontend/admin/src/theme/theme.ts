// Light/dark theme switching (docs/plans/t9-theming.md, "Theme switching"). The theme is
// `<html data-theme="light|dark">`; tokens.css defines the colours for each. One choice is shared
// by all three apps on the same origin (localStorage `buzzer-theme`); with nothing stored, the app
// follows the OS and keeps following it. Other open tabs pick a new choice up on their next load.
// Byte-identical in host, player and admin (tests/unit/test_theme_copies.py). The inline script in
// each index.html does the first apply with the same key and rule, before React loads.

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'buzzer-theme';
const OS_DARK = '(prefers-color-scheme: dark)';

/** The saved choice, or null ("follow the OS") for no value, any other value or a storage error. */
export function getStoredTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function osTheme(): Theme {
  return typeof window.matchMedia === 'function' && window.matchMedia(OS_DARK).matches ? 'dark' : 'light';
}

/** The saved choice, else the OS preference. */
export function currentTheme(): Theme {
  return getStoredTheme() ?? osTheme();
}

/** A token as an opaque CSS colour, e.g. tokenColor('page') → "rgb(17 19 24)". The only way code
 * outside CSS gets a colour (the theme-color meta tag, the plot canvases). */
export function tokenColor(name: string): string {
  const channels = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
  return `rgb(${channels})`;
}

/** Show a theme: data-theme, color-scheme, the theme-color meta tag, then a `themechange` event. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = tokenColor('page');
  window.dispatchEvent(new Event('themechange'));
}

/** Save a choice (ignoring storage errors) and show it. */
export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Storage blocked: the choice still applies to this page.
  }
  applyTheme(theme);
}

/** Call once before React renders: show the current theme and, while nothing is saved, follow
 * OS changes. */
export function initTheme(): void {
  applyTheme(currentTheme());
  if (typeof window.matchMedia !== 'function') return;
  window.matchMedia(OS_DARK).addEventListener('change', () => {
    if (getStoredTheme() === null) applyTheme(osTheme());
  });
}
