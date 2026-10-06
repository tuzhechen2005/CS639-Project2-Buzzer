// @vitest-environment jsdom
// Tests for src/theme/theme.ts (docs/plans/t9-theming.md, "Theme switching"). The file lives in
// lib/, not theme/, so src/theme/ stays byte-identical across the three apps. jsdom does not load
// tokens.css, so tests that read a token set it inline on <html> first.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, currentTheme, getStoredTheme, initTheme, setTheme, tokenColor } from '../theme/theme';

const KEY = 'buzzer-theme';

/** Stub the OS preference; `set` changes it and notifies listeners, like a real OS switch. */
function stubOs(dark: boolean) {
  const state = { dark };
  const listeners: (() => void)[] = [];
  const query = {
    get matches() {
      return state.dark;
    },
    addEventListener: (_type: string, listener: () => void) => listeners.push(listener),
  };
  vi.stubGlobal('matchMedia', () => query);
  return {
    set(next: boolean) {
      state.dark = next;
      listeners.forEach((listener) => listener());
    },
  };
}

function addThemeColorMeta(): HTMLMetaElement {
  const meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = '';
  document.head.appendChild(meta);
  return meta;
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.head.innerHTML = '';
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('style');
});

describe('the stored choice and the OS', () => {
  it('uses the stored choice over the OS', () => {
    stubOs(true);
    localStorage.setItem(KEY, 'light');
    expect(getStoredTheme()).toBe('light');
    expect(currentTheme()).toBe('light');
  });

  it('follows the OS when nothing is stored', () => {
    stubOs(false);
    expect(getStoredTheme()).toBeNull();
    expect(currentTheme()).toBe('light');
    stubOs(true);
    expect(currentTheme()).toBe('dark');
  });

  it('treats an invalid stored value as "follow the OS"', () => {
    stubOs(true);
    localStorage.setItem(KEY, 'blue');
    expect(getStoredTheme()).toBeNull();
    expect(currentTheme()).toBe('dark');
  });

  it('falls back to the OS when storage throws', () => {
    stubOs(true);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(getStoredTheme()).toBeNull();
    expect(currentTheme()).toBe('dark');
  });
});

describe('applyTheme', () => {
  it('sets data-theme, color-scheme and the theme-color meta, then fires themechange', () => {
    document.documentElement.style.setProperty('--page', ' 1 2 3');
    const meta = addThemeColorMeta();
    const onChange = vi.fn();
    window.addEventListener('themechange', onChange);

    applyTheme('dark');

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(meta.content).toBe('rgb(1 2 3)');
    expect(onChange).toHaveBeenCalledTimes(1);
    window.removeEventListener('themechange', onChange);
  });

  it('keeps color-scheme dark for the light theme until the light values exist (T9 step 1)', () => {
    // When step 7 of the spec's order puts the light values in tokens.css, this expects 'light'.
    applyTheme('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('dark');
  });

  it('never creates a theme-color meta tag', () => {
    applyTheme('dark');
    expect(document.querySelector('meta[name="theme-color"]')).toBeNull();
  });

  it('reads tokens as opaque rgb() colours', () => {
    document.documentElement.style.setProperty('--surface', ' 26 29 36');
    expect(tokenColor('surface')).toBe('rgb(26 29 36)');
  });
});

describe('setTheme', () => {
  it('saves the choice and applies it', () => {
    setTheme('dark');
    expect(localStorage.getItem(KEY)).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('still applies the choice when storage throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});

describe('initTheme', () => {
  it('applies the current theme', () => {
    stubOs(true);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('follows OS changes only while nothing is stored', () => {
    const os = stubOs(false);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe('light');

    os.set(true);
    expect(document.documentElement.dataset.theme).toBe('dark');

    setTheme('light');
    os.set(true);
    os.set(false);
    os.set(true);
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
