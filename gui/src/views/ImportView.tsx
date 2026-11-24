import { useCallback, useRef, useState } from 'react';
import { api, readFileAsBase64, trader } from '../api';
import type { Extraction, UploadResult } from '../types';
import { Banner, Panel } from '../components/common';
import { useI18n } from '../i18n';
import { useLegacyI18n } from '../locales/legacy';

// Import flow: pick a file, let the local engine read it, correct every field,
// then commit. The raw file is stored once, keyed by hash, and never leaves
// this machine.

interface DraftRow {
  trade_date: string;
  trade_time: string;
  symbol: string;
  name: string;
  side: string;
  price: string;
  quantity: string;
  fee: string;
  thesis: string;
}

const EMPTY_ROW: DraftRow = {
  trade_date: '', trade_time: '', symbol: '', name: '', side: 'BUY', price: '', quantity: '', fee: '', thesis: '',
};

/** Strictly offline synthetic fills for first-run walkthroughs (no real tickers). */
const TOY_SAMPLE_ROWS: DraftRow[] = [
  { trade_date: '2026-06-01', trade_time: '09:42:00', symbol: 'TOY.CUB', name: 'Toy Cub A', side: 'BUY', price: '10.00', quantity: '1000', fee: '5.00', thesis: 'First pullback to opening range; invalidation 9.40' },
  { trade_date: '2026-06-02', trade_time: '10:15:00', symbol: 'TOY.CUB', name: 'Toy Cub A', side: 'SELL', price: '10.85', quantity: '1000', fee: '5.40', thesis: 'D1 target reached; scaled out cleanly' },
  { trade_date: '2026-06-03', trade_time: '13:20:00', symbol: 'TOY.ALPHA', name: 'Toy Alpha', side: 'BUY', price: '22.40', quantity: '500', fee: '5.60', thesis: 'Breakout probe; invalidation 21.60' },
  { trade_date: '2026-06-04', trade_time: '14:40:00', symbol: 'TOY.ALPHA', name: 'Toy Alpha', side: 'SELL', price: '21.30', quantity: '500', fee: '5.30', thesis: 'Exited past invalidation; review chase timing' },
  { trade_date: '2026-06-05', trade_time: '09:50:00', symbol: 'TOY.CUB', name: 'Toy Cub A', side: 'BUY', price: '11.10', quantity: '1000', fee: '5.55', thesis: 'Leader re-test; invalidation 10.60' },
  { trade_date: '2026-06-08', trade_time: '11:05:00', symbol: 'TOY.CUB', name: 'Toy Cub A', side: 'SELL', price: '11.90', quantity: '1000', fee: '5.95', thesis: 'Followed plan into volume expansion' },
  { trade_date: '2026-06-09', trade_time: '10:05:00', symbol: 'TOY.BETA', name: 'Toy Beta', side: 'BUY', price: '15.20', quantity: '800', fee: '6.08', thesis: 'Divergence reversal setup; invalidation 14.70' },
  { trade_date: '2026-06-10', trade_time: '14:10:00', symbol: 'TOY.BETA', name: 'Toy Beta', side: 'SELL', price: '16.05', quantity: '800', fee: '6.42', thesis: 'D1 momentum follow-through' },
];

export function ImportView({
  onImported,
  onGoToOverview,
  onGoToInsight,
}: {
  onImported: () => void;
  onGoToOverview?: () => void;
  onGoToInsight?: () => void;
}) {
  const { t } = useLegacyI18n();
  const { t: shellT } = useI18n();
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [status, setStatus] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [importedOnce, setImportedOnce] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const applyExtraction = (result: UploadResult) => {
    setUpload(result);
    setRows(
      result.extraction.rows.map((row) => ({
        trade_date: row.trade_date || '',
        trade_time: row.trade_time || '',
        symbol: row.symbol || '',
        name: row.name || '',
        side: row.side || 'BUY',
        price: row.price === null ? '' : String(row.price),
        quantity: row.quantity === null ? '' : String(row.quantity),
        fee: row.fee === null || row.fee === undefined ? '' : String(row.fee),
        thesis: row.thesis || '',
      })),
    );
  };

  const loadToySample = () => {
    setUpload(null);
    setError('');
    setImportedOnce(false);
    setRows(TOY_SAMPLE_ROWS.map((item) => ({ ...item })));
    setStatus(shellT('import.toy.loaded', { count: TOY_SAMPLE_ROWS.length }));
  };

  const handleFile = useCallback(async (file: File) => {
    setBusy(true);
    setError('');
    setStatus('');
    setImportedOnce(false);
    try {
      const content_base64 = await readFileAsBase64(file);
      const result = await api.upload({ file_name: file.name, media_type: file.type, content_base64 });
      applyExtraction(result);
      setStatus(t('import.parsed', { count: result.extraction.row_count, engine: result.extraction.engine }));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : String(uploadError));
    } finally {
      setBusy(false);
    }
  }, [t]);

  const submit = async () => {
    if (rows.length === 0) return;
    setBusy(true);
    setError('');
    try {
      // Write into the tenant journal, which is the store every view reads. The
      // workbench commit route writes to a different database, so imported rows
      // used to land somewhere the dashboard never looked — and in hosted mode
      // an unpartitioned local file, outside tenant isolation entirely.
      const result = await trader.importTrades({
        rows: rows.map((row) => ({
          trade_id: [row.trade_date, row.trade_time, row.symbol, row.side].join('-'),
          symbol: row.symbol,
          name: row.name,
          side: row.side,
          price: row.price === '' ? null : Number(row.price),
          quantity: row.quantity === '' ? null : Number(row.quantity),
          fee: row.fee === '' ? 0 : Number(row.fee),
          trade_date: row.trade_date,
          trade_time: row.trade_time,
          thesis: row.thesis,
        })),
      });
      setStatus(t('import.written', { inserted: result.inserted_count, updated: result.updated_count }));
      setUpload(null);
      setRows([]);
      setImportedOnce(true);
      onImported();
    } catch (commitError) {
      setError(commitError instanceof Error ? commitError.message : String(commitError));
    } finally {
      setBusy(false);
    }
  };

  const addManual = async (row: DraftRow) => {
    setBusy(true);
    setError('');
    try {
      await trader.importTrades({
        rows: [{
          trade_id: [row.trade_date, row.trade_time, row.symbol, row.side].join('-'),
          symbol: row.symbol,
          name: row.name,
          side: row.side,
          price: row.price === '' ? null : Number(row.price),
          quantity: row.quantity === '' ? null : Number(row.quantity),
          fee: row.fee === '' ? 0 : Number(row.fee),
          trade_date: row.trade_date,
          trade_time: row.trade_time,
          thesis: row.thesis,
        }],
      });
      setStatus(t('import.done'));
      setImportedOnce(true);
      onImported();
      return true;
    } catch (manualError) {
      setError(manualError instanceof Error ? manualError.message : String(manualError));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel
        title={t('import.title')}
        actions={(
          <button className="ghost" onClick={loadToySample} disabled={busy} data-testid="load-toy-sample">
            {shellT('import.toy.cta')}
          </button>
        )}
      >
        <div
          className={'drop' + (dragging ? ' over' : '')}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files?.[0];
            if (file) void handleFile(file);
          }}
          onClick={() => inputRef.current?.click()}
          style={{ cursor: 'pointer' }}
        >
          {busy ? t('import.busy') : t('import.drop')}
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {t('import.localOnly')}
          </div>
          <input
            ref={inputRef}
            type="file"
            style={{ display: 'none' }}
            accept=".csv,.tsv,.txt,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.xls,.xlsx,.json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
              event.target.value = '';
            }}
          />
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          {shellT('import.toy.hint')}
        </div>
        {status ? <div className="status-line ok" role="status" style={{ marginTop: 10 }}>{status}</div> : null}
        {importedOnce && (onGoToOverview || onGoToInsight) ? (
          <div className="import-success-bar" data-testid="import-next-steps">
            <span>{shellT('import.next.title')}</span>
            <div className="row">
              {onGoToOverview ? (
                <button className="primary" onClick={onGoToOverview}>{shellT('import.next.overview')}</button>
              ) : null}
              {onGoToInsight ? (
                <button className="ghost" onClick={onGoToInsight}>{shellT('import.next.insight')}</button>
              ) : null}
            </div>
          </div>
        ) : null}
        {error ? <div className="banner-error" role="alert" style={{ marginTop: 10 }}><Banner>{error}</Banner></div> : null}
        {upload && upload.extraction.status === 'engine_missing' ? (
          <div style={{ marginTop: 10 }}>
            <Banner>
              {t('import.ocrMissing')}
              <code style={{ marginLeft: 6 }}>pip install "smartmoney-cub-harness[ocr]"</code>
            </Banner>
          </div>
        ) : null}
      </Panel>

      {rows.length > 0 ? (
        <Panel
          title={t('import.review', { count: rows.length })}
          actions={<button className="primary" onClick={submit} disabled={busy}>{t('import.confirm')}</button>}
        >
          <ExtractionTable rows={rows} extraction={upload?.extraction || null} onChange={setRows} />
        </Panel>
      ) : null}

      <ManualEntry onSubmit={addManual} busy={busy} />
    </div>
  );
}

function ExtractionTable({ rows, extraction, onChange }: {
  rows: DraftRow[];
  extraction: Extraction | null;
  onChange: (rows: DraftRow[]) => void;
}) {
  const { t } = useLegacyI18n();
  const { t: shellT } = useI18n();
  const update = (index: number, key: keyof DraftRow, value: string) => {
    onChange(rows.map((row, position) => (position === index ? { ...row, [key]: value } : row)));
  };
  const candidates = extraction?.rows || [];
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th>{t('import.date')}</th><th>{t('import.time')}</th><th>{t('import.code')}</th><th>{t('playbook.name')}</th><th>{t('import.direction')}</th>
            <th>{t('import.price')}</th><th>{t('import.quantity')}</th><th>{t('import.fee')}</th><th>{t('import.confidence')}</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const confidence = candidates[index]?.field_confidence || {};
            const lowest = Math.min(...Object.values(confidence).concat(1));
            return (
              <tr key={index}>
                <td><input style={{ width: 108 }} value={row.trade_date} onChange={(event) => update(index, 'trade_date', event.target.value)} /></td>
                <td><input style={{ width: 84 }} value={row.trade_time} onChange={(event) => update(index, 'trade_time', event.target.value)} /></td>
                <td><input style={{ width: 96 }} value={row.symbol} onChange={(event) => update(index, 'symbol', event.target.value)} /></td>
                <td><input style={{ width: 96 }} value={row.name} onChange={(event) => update(index, 'name', event.target.value)} /></td>
                <td>
                  <select value={row.side} onChange={(event) => update(index, 'side', event.target.value)}>
                    <option value="BUY">{t('import.buy')}</option>
                    <option value="SELL">{t('import.sell')}</option>
                  </select>
                </td>
                <td><input style={{ width: 84 }} value={row.price} onChange={(event) => update(index, 'price', event.target.value)} /></td>
                <td><input style={{ width: 92 }} value={row.quantity} onChange={(event) => update(index, 'quantity', event.target.value)} /></td>
                <td><input style={{ width: 72 }} value={row.fee} onChange={(event) => update(index, 'fee', event.target.value)} /></td>
                <td>
                  {lowest >= 0.85 ? <span className="badge ok">{shellT('import.confidence.high')}</span>
                    : lowest >= 0.6 ? <span className="badge warn">{shellT('import.confidence.medium')}</span>
                      : <span className="badge error">{shellT('import.confidence.low')}</span>}
                </td>
                <td>
                  <button className="ghost" onClick={() => onChange(rows.filter((_, position) => position !== index))}>{t('import.delete')}</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ManualEntry({ onSubmit, busy }: { onSubmit: (row: DraftRow) => Promise<boolean>; busy: boolean }) {
  const { t } = useLegacyI18n();
  const { t: shellT } = useI18n();
  const [row, setRow] = useState<DraftRow>({ ...EMPTY_ROW });
  const [validationError, setValidationError] = useState('');
  const update = (key: keyof DraftRow, value: string) => {
    setValidationError('');
    setRow((prev) => ({ ...prev, [key]: value }));
  };
  return (
    <Panel title={t('import.manual')}>
      <div className="row">
        <div className="field"><label>{t('import.date')}</label><input value={row.trade_date} onChange={(event) => update('trade_date', event.target.value)} placeholder="2026-09-01" /></div>
        <div className="field"><label>{t('import.time')}</label><input value={row.trade_time} onChange={(event) => update('trade_time', event.target.value)} placeholder="09:35:00" /></div>
        <div className="field"><label>{t('import.code')}</label><input style={{ width: 90 }} value={row.symbol} onChange={(event) => update('symbol', event.target.value)} placeholder="TOY.CUB" /></div>
        <div className="field"><label>{t('playbook.name')}</label><input value={row.name} onChange={(event) => update('name', event.target.value)} /></div>
        <div className="field">
          <label>{t('import.direction')}</label>
          <select value={row.side} onChange={(event) => update('side', event.target.value)}>
            <option value="BUY">{t('import.buy')}</option><option value="SELL">{t('import.sell')}</option>
          </select>
        </div>
        <div className="field"><label>{t('import.price')}</label><input style={{ width: 90 }} value={row.price} onChange={(event) => update('price', event.target.value)} placeholder="10.00" /></div>
        <div className="field"><label>{t('import.quantity')}</label><input style={{ width: 100 }} value={row.quantity} onChange={(event) => update('quantity', event.target.value)} placeholder="1000" /></div>
        <div className="field"><label>{t('import.fee')}</label><input style={{ width: 80 }} value={row.fee} onChange={(event) => update('fee', event.target.value)} placeholder="5.00" /></div>
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            const price = Number(row.price);
            const qty = Number(row.quantity);
            if (!row.trade_date.trim() || !row.symbol.trim() || !Number.isFinite(price) || price <= 0 || !Number.isFinite(qty) || qty <= 0) {
              setValidationError(shellT('import.validation.required'));
              return;
            }
            if (await onSubmit(row)) setRow({ ...EMPTY_ROW });
          }}
        >
          {t('import.reentry')}
        </button>
      </div>
      {validationError ? <div className="notice" role="alert" style={{ marginTop: 10 }}>{validationError}</div> : null}
    </Panel>
  );
}
