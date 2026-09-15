/**
 * A candlestick chart drawn as inline SVG.
 *
 * Why not a charting library: the interface ships inside the Python package so
 * an installed copy works offline, and a charting dependency would be the only
 * third-party runtime code in the build. `dependencies` in package.json stays
 * React-only, which a test asserts.
 *
 * The component is a pure function of its props. It holds no state, reads no
 * clock, and derives both scales from the bars it is given, so the same props
 * always draw the same geometry.
 */

export interface CandleMarker {
  /** Optional stable identity, carried through from a stored marker. */
  marker_id?: string;
  /** Bar timestamp the marker is anchored to, matched against open_time. */
  time: string;
  price: number;
  /** `exit` is drawn neutrally; anything else reads as an entry. */
  kind?: string;
  label?: string;
}

/**
 * The minimum a bar has to carry.
 *
 * Structural rather than the full MarketBar shape, so a line series — an equity
 * curve, one value per point — can be passed directly instead of inventing an
 * open, high, and low the data never had.
 */
export interface ChartBar {
  open_time: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
}

export interface CandleChartProps {
  bars: ChartBar[];
  width?: number;
  height?: number;
  markers?: CandleMarker[];
  /**
   * `candles` draws an OHLC body and wick per bar. `line` draws one path
   * through the close values, for a series where a candle per point would
   * depict a range that does not exist.
   */
  variant?: 'candles' | 'line';
  /** Shown in place of the plot when there is nothing to draw. */
  emptyText?: string;
}

const PADDING = { top: 10, right: 58, bottom: 22, left: 8 };
const MIN_BODY_HEIGHT = 1;
const X_TICK_TARGET = 6;
const Y_TICK_TARGET = 5;
const MAX_Y_TICKS = 12;

/** A number the chart can plot, tolerating null and numeric strings. */
function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function CandleChart({
  bars,
  width = 720,
  height = 300,
  markers = [],
  variant = 'candles',
  emptyText = '没有可绘制的行情数据',
}: CandleChartProps) {
  const line = variant === 'line';
  const highOf = (bar: ChartBar) => (line ? number(bar.close) : number(bar.high));
  const lowOf = (bar: ChartBar) => (line ? number(bar.close) : number(bar.low));

  // A candle mode bar without a real open/high/low would be drawn from zeros.
  // Unusable bars are dropped before anything is measured, because one bad value
  // would otherwise set the whole scale rather than spoil one shape.
  const usable = bars.filter(
    (bar) =>
      Boolean(bar) && typeof bar.open_time === 'string' && Number.isFinite(number(bar.close)) &&
      (line || (
        Number.isFinite(number(bar.open)) &&
        Number.isFinite(number(bar.high)) &&
        Number.isFinite(number(bar.low))
      )),
  );
  if (!usable.length) {
    return <div className="empty" style={{ minHeight: 120 }}>{emptyText}</div>;
  }

  const plotWidth = Math.max(1, width - PADDING.left - PADDING.right);
  const plotHeight = Math.max(1, height - PADDING.top - PADDING.bottom);
  const top = Math.max(...usable.map(highOf));
  const bottom = Math.min(...usable.map(lowOf));
  // A flat series (every bar at one price) would divide by zero; one narrow
  // range keeps the shapes on the chart instead of off the top edge.
  const span = top - bottom || Math.max(1e-6, Math.abs(top) * 0.01) || 1;

  const toY = (price: number) => PADDING.top + ((top - price) / span) * plotHeight;
  const slot = plotWidth / usable.length;
  const bodyWidth = Math.max(1, Math.min(slot * 0.7, 14));
  const toX = (index: number) => PADDING.left + slot * (index + 0.5);

  const ticks = axisTicks(top, bottom, Y_TICK_TARGET);
  const labelStep = Math.max(1, Math.ceil(usable.length / X_TICK_TARGET));
  const linePath = usable
    .map((bar, index) => (index === 0 ? 'M' : 'L') + toX(index).toFixed(2) + ' ' + toY(number(bar.close)).toFixed(2))
    .join(' ');

  // Markers are matched by timestamp: a caller draws them from trade rows that
  // carry a time, not an index into this particular series.
  const indexByTime = new Map(usable.map((bar, index) => [bar.open_time, index]));
  const placed = markers
    .map((marker) => {
      const index = indexByTime.get(marker.time);
      if (index === undefined || !Number.isFinite(marker.price)) return null;
      return { ...marker, x: toX(index), y: toY(marker.price) };
    })
    .filter((marker): marker is CandleMarker & { x: number; y: number } => marker !== null);

  return (
    <svg
      viewBox={'0 0 ' + width + ' ' + height}
      width="100%"
      height={height}
      role="img"
      aria-label={(line ? '折线图' : '蜡烛图') + '，共 ' + usable.length + ' 个点'}
      style={{ display: 'block', overflow: 'visible' }}
    >
      {ticks.map((tick) => (
        <g key={'y-' + tick}>
          <line
            x1={PADDING.left} y1={toY(tick)}
            x2={PADDING.left + plotWidth} y2={toY(tick)}
            className="chart-grid" strokeWidth="1"
          />
          <text x={PADDING.left + plotWidth + 6} y={toY(tick) + 3.5} className="chart-axis" fontSize="10">
            {formatPrice(tick, span)}
          </text>
        </g>
      ))}

      {line ? (
        <path
          d={linePath}
          className={
            'chart-line ' +
            (number(usable[usable.length - 1].close) >= number(usable[0].close) ? 'candle-up' : 'candle-down')
          }
          fill="none"
          strokeWidth="1.5"
        />
      ) : null}

      {!line
        ? usable.map((bar, index) => {
            // The candle colour is fixed: rising red, falling green, the A-share
            // convention and this product's default. The journal's red-up /
            // green-up toggle is deliberately not applied here — the chart is a
            // pure function of its props, and threading a display preference
            // through would re-render every series on a preference change.
            const rising = number(bar.close) >= number(bar.open);
            // Colours come from classes, not presentation attributes:
            // `stroke="var(--pos)"` is not a value the SVG attribute grammar
            // accepts, while a class resolves through the cascade everywhere.
            const toneClass = rising ? 'candle-up' : 'candle-down';
            const bodyTop = toY(Math.max(number(bar.open), number(bar.close)));
            const bodyBottom = toY(Math.min(number(bar.open), number(bar.close)));
            const centerX = toX(index);
            return (
              <g key={bar.open_time + '-' + index}>
                <line
                  x1={centerX} y1={toY(number(bar.high))} x2={centerX} y2={toY(number(bar.low))}
                  className={'candle-wick ' + toneClass} strokeWidth="1"
                />
                <rect
                  x={centerX - bodyWidth / 2} y={bodyTop}
                  width={bodyWidth} height={Math.max(MIN_BODY_HEIGHT, bodyBottom - bodyTop)}
                  className={'candle-body ' + toneClass} strokeWidth="0.5"
                />
              </g>
            );
          })
        : null}

      {usable.map((bar, index) =>
        index % labelStep === 0 || index === usable.length - 1 ? (
          <text
            key={'x-' + bar.open_time}
            x={toX(index)} y={height - 6}
            className="chart-axis" fontSize="10" textAnchor="middle"
          >
            {shortTime(bar.open_time)}
          </text>
        ) : null,
      )}

      {placed.map((marker, index) => {
        const entry = marker.kind !== 'exit';
        const toneClass = entry ? 'marker-entry' : 'marker-exit';
        return (
          <g key={(marker.marker_id || marker.time) + '-' + index}>
            <circle cx={marker.x} cy={marker.y} r="3.5" className={'marker-dot ' + toneClass} strokeWidth="1" />
            {marker.label ? (
              <text x={marker.x + 6} y={marker.y - 5} className={'marker-label ' + toneClass} fontSize="10">
                {marker.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/** Evenly spaced gridlines, snapped to round numbers where the range allows. */
function axisTicks(top: number, bottom: number, count: number): number[] {
  const span = top - bottom || 1;
  const rawStep = span / count;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const normalized = rawStep / magnitude;
  const niceStep = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const first = Math.ceil(bottom / niceStep) * niceStep;
  const ticks: number[] = [];
  for (let value = first; value <= top + niceStep * 0.001 && ticks.length < MAX_Y_TICKS; value += niceStep) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks.length ? ticks : [bottom, top];
}

/** Axis precision follows the visible range, so a 0.5 range does not read as
 *  three identical integers. */
function formatPrice(value: number, span: number): string {
  const digits = span >= 100 ? 0 : span >= 1 ? 2 : span >= 0.01 ? 4 : 6;
  return value.toFixed(digits);
}

/** A compact axis label: clock time for intraday bars, month-day otherwise. */
function shortTime(openTime: string): string {
  const text = String(openTime || '');
  const [date, clock] = text.split('T');
  if (clock) return clock.slice(0, 5);
  return date.length >= 10 ? date.slice(5) : date;
}
