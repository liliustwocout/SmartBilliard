import { useState } from 'react';
import { applyTheme, currentTheme } from '../theme';
import type { Theme } from '../theme';
import { Button } from './components';

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button variant="ghost" size="sm" aria-label={`Chuyển sang giao diện ${next === 'dark' ? 'tối' : 'sáng'}`}
      onClick={() => { applyTheme(next); setTheme(next); }}>
      {theme === 'dark' ? '☀ Sáng' : '☾ Tối'}
    </Button>
  );
}
