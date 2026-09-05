import React, { createContext, useContext, useMemo, useState } from 'react';
import { Colors, darkColors, lightColors } from './tokens';

type Scheme = 'dark' | 'light';

type ThemeValue = {
  scheme: Scheme;
  colors: Colors;
  toggleScheme: () => void;
};

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [scheme, setScheme] = useState<Scheme>('dark');

  const value = useMemo<ThemeValue>(
    () => ({
      scheme,
      colors: scheme === 'dark' ? darkColors : lightColors,
      toggleScheme: () => setScheme((s) => (s === 'dark' ? 'light' : 'dark')),
    }),
    [scheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
