import type { OddsFormat } from '@/lib/types';

function gcd(a: number, b: number): number {
  a = Math.abs(Math.round(a));
  b = Math.abs(Math.round(b));
  while (b) {
    const t = b;
    b = a % b;
    a = t;
  }
  return a;
}

export function formatOdds(probability: number, format: OddsFormat): string {
  if (probability <= 0) probability = 0.001;
  if (probability >= 1) probability = 0.999;

  switch (format) {
    case 'percentage':
      return `${(probability * 100).toFixed(1)}%`;

    case 'decimal': {
      const decimal = 1 / probability;
      return decimal.toFixed(2);
    }

    case 'fractional': {
      const denominator = 100;
      const numerator = Math.round(probability * denominator);
      const remainder = denominator - numerator;
      if (remainder <= 0) return '1/1';
      const d = gcd(numerator, remainder);
      // fractional odds are (1 - p) / p simplified
      // but commonly shown as numerator/denominator where numerator = profit on denominator stake
      const fracNum = Math.round((1 - probability) * 100);
      const fracDen = Math.round(probability * 100);
      const g = gcd(fracNum, fracDen);
      if (g === 0) return '1/1';
      return `${fracNum / g}/${fracDen / g}`;
    }

    default:
      return `${(probability * 100).toFixed(1)}%`;
  }
}
