'use client';

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import type { OddsFormat } from '@/lib/types';

interface OddsFormatContextValue {
  oddsFormat: OddsFormat;
  setOddsFormat: (fmt: OddsFormat) => void;
}

const OddsFormatContext = createContext<OddsFormatContextValue>({
  oddsFormat: 'percentage',
  setOddsFormat: () => {},
});

export function OddsFormatProvider({ children }: { children: ReactNode }) {
  const [oddsFormat, setOddsFormatState] = useState<OddsFormat>('percentage');

  useEffect(() => {
    const stored = localStorage.getItem('oddsFormat') as OddsFormat | null;
    if (stored && ['percentage', 'decimal', 'fractional'].includes(stored)) {
      setOddsFormatState(stored);
    }
  }, []);

  const setOddsFormat = (fmt: OddsFormat) => {
    setOddsFormatState(fmt);
    localStorage.setItem('oddsFormat', fmt);
  };

  return (
    <OddsFormatContext.Provider value={{ oddsFormat, setOddsFormat }}>
      {children}
    </OddsFormatContext.Provider>
  );
}

export function useOddsFormat() {
  return useContext(OddsFormatContext);
}
