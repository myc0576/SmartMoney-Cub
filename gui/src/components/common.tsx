import React from 'react';

export function formatMoney(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** A cost total is never presented with a leading plus sign. */
export function formatCost(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + value.toFixed(2) + '%';
}

export function toneOf(value: number | null | undefined, scheme: 'cn' | 'intl'): string {
  if (value === null || value === undefined || value === 0) return '';
  const positive = value > 0;
  const useUp = scheme === 'cn' ? positive : !positive;
  return useUp ? 'up' : 'down';
}

export function Panel({ title, children, actions }: { title?: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <section className="panel">
      {title ? (
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Kpi({ label, value, note, tone }: { label: string; value: React.ReactNode; note?: string; tone?: string }) {
  return (
    <div className="panel">
      <div className="kpi-label">{label}</div>
      <div className={'kpi-value ' + (tone || '')}>{value}</div>
      {note ? <div className="kpi-note">{note}</div> : null}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

export function Badge({ kind, children }: { kind: 'ok' | 'warn' | 'error'; children: React.ReactNode }) {
  return <span className={'badge ' + kind}>{children}</span>;
}

export function Banner({ children }: { children: React.ReactNode }) {
  return <div className="notice">{children}</div>;
}

// A tiny inline sparkline. Charts stay dependency-free so the built interface
// works in a fully offline install.
export function Sparkline({ points, scheme }: { points: number[]; scheme: 'cn' | 'intl' }) {
  if (points.length < 2) return <div className="muted">至少需要 2 笔平仓交易才能绘制曲线</div>;
  const width = 620;
  const height = 120;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => (index === 0 ? 'M' : 'L') + (index * step).toFixed(1) + ' ' + (height - ((value - min) / span) * height).toFixed(1))
    .join(' ');
  const last = points[points.length - 1];
  // The rising/falling colour of the curve follows the same preference the
  // tables use, so the chart and the numbers never disagree about which
  // direction is red.
  const toneClass = last === 0 ? 'spark-flat' : ((last > 0) === (scheme === 'cn') ? 'spark-up' : 'spark-down');
  const zeroY = height - ((0 - min) / span) * height;
  return (
    <svg viewBox={'0 0 ' + width + ' ' + height} style={{ width: '100%', height: 140 }}>
      <line x1="0" y1={zeroY} x2={width} y2={zeroY} className="chart-grid" strokeDasharray="3 4" />
      <path d={path} fill="none" className={'spark-line ' + toneClass} strokeWidth="2" />
    </svg>
  );
}

export function Bars({ rows, scheme, labelOf }: {
  rows: { key: string; name?: string; is_st?: boolean; net_pnl: number; trade_count: number; small_sample: boolean }[];
  scheme: 'cn' | 'intl';
  labelOf?: (row: { key: string; name?: string; is_st?: boolean }) => any;
}) {
  if (!rows.length) return <Empty text="暂无可归因的样本" />;
  const max = Math.max(...rows.map((row) => Math.abs(row.net_pnl)), 1);
  return (
    <div className="grid" style={{ gap: 8 }}>
      {rows.map((row) => {
        const isSt = row.is_st || (row.name && row.name.toUpperCase().includes('ST'));
        return (
          <div key={row.key} className="row" style={{ gap: 10 }}>
            <div
              style={{ width: 170, flex: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              className="muted"
              title={row.name ? (row.key + ' ' + row.name) : row.key}
            >
              {labelOf ? labelOf(row) : (
                <span>
                  <span style={{ fontWeight: 600, color: 'var(--text)' }}>{row.key}</span>
                  {row.name ? <span style={{ marginLeft: 6 }}>{row.name}</span> : null}
                  {isSt ? <span className="badge warn" style={{ marginLeft: 5, fontSize: 10, padding: '0 4px', verticalAlign: 'middle' }}>ST</span> : null}
                </span>
              )}
              {row.small_sample ? ' *' : ''}
            </div>
          <div style={{ flex: 1 }}>
            <div className={'bar ' + (row.net_pnl >= 0 ? 'gain' : 'loss')}>
              <span style={{ width: Math.max(3, (Math.abs(row.net_pnl) / max) * 100) + '%' }} />
            </div>
          </div>
          <div className={'num ' + toneOf(row.net_pnl, scheme)} style={{ width: 96, textAlign: 'right' }}>
            {formatMoney(row.net_pnl)}
          </div>
          <div className="muted" style={{ width: 56, textAlign: 'right' }}>
            {row.trade_count} 笔
          </div>
        </div>
        );
      })}
    </div>
  );
}


/**
 * Render the small subset of Markdown a review answer uses: headings, bullet
 * lists, bold runs, and inline code. Enough structure to read comfortably,
 * without pulling in a parser dependency for a local offline interface.
 */
export function Markdown({ text }: { text: string }) {
  const lines = text.split('\n');
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (!bullets.length) return;
    blocks.push(
      <ul key={'ul-' + blocks.length} style={{ margin: '4px 0', paddingLeft: 18 }}>
        {bullets.map((item, index) => (
          <li key={index} style={{ marginBottom: 2 }}>{inline(item)}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };

  lines.forEach((raw, index) => {
    const line = raw.trimEnd();
    if (line.startsWith('- ') || line.startsWith('* ')) {
      bullets.push(line.slice(2));
      return;
    }
    flush();
    if (!line.trim()) return;
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      blocks.push(
        <div
          key={'h-' + index}
          style={{ fontWeight: 600, margin: index === 0 ? '0 0 6px' : '10px 0 4px', fontSize: level <= 2 ? 13 : 12.5 }}
        >
          {inline(heading[2])}
        </div>,
      );
      return;
    }
    blocks.push(
      <div key={'p-' + index} style={{ margin: '3px 0' }}>{inline(line)}</div>,
    );
  });
  flush();
  return <>{blocks}</>;
}

function inline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\`[^\`]+\`)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('\`') && part.endsWith('\`')) {
      return (
        <code key={index} style={{ background: 'var(--inset)', padding: '1px 4px', borderRadius: 4 }}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={index}>{part}</span>;
  });
}
