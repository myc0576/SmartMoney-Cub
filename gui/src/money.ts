/** Never manufacture a common unit or treat absent P&L as zero. */
export function monetaryTotal(rows: readonly { currency?: string | null; net_pnl?: number | null }[]): number | null {
  if (!rows.length) return 0;
  const currencies = new Set(rows.map(row => row.currency?.trim().toUpperCase()));
  if (currencies.size !== 1 || currencies.has(undefined) || currencies.has('') || currencies.has('UNKNOWN')) return null;
  if (rows.some(row => row.net_pnl == null || !Number.isFinite(row.net_pnl))) return null;
  return rows.reduce((sum, row) => sum + row.net_pnl!, 0);
}

export function currencyTotals(rows: readonly { currency?: string | null; net_pnl?: number | null }[]) {
  const buckets = new Map<string, typeof rows[number][]>();
  for (const row of rows) {
    const currency = row.currency || 'UNKNOWN';
    buckets.set(currency, [...(buckets.get(currency) || []), row]);
  }
  return [...buckets.entries()].map(([currency, entries]) => ({ currency, value: monetaryTotal(entries) }));
}
