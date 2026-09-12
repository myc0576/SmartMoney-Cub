import { useCallback, useRef, useState } from 'react';
import { api, readFileAsBase64 } from '../api';
import type { Extraction, UploadResult } from '../types';
import { Banner, Panel } from '../components/common';

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

export function ImportView({ onImported }: { onImported: () => void }) {
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [status, setStatus] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
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
        fee: '',
        thesis: '',
      })),
    );
  };

  const handleFile = useCallback(async (file: File) => {
    setBusy(true);
    setError('');
    setStatus('');
    try {
      const content_base64 = await readFileAsBase64(file);
      const result = await api.upload({ file_name: file.name, media_type: file.type, content_base64 });
      applyExtraction(result);
      setStatus('已解析 ' + result.extraction.row_count + ' 行，引擎：' + result.extraction.engine + '。请逐行确认后再提交。');
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : String(uploadError));
    } finally {
      setBusy(false);
    }
  }, []);

  const submit = async () => {
    if (!upload) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.commitImport({
        extraction_id: upload.extraction.extraction_id,
        document_id: upload.document.document_id,
        rows: rows.map((row) => ({
          ...row,
          price: row.price === '' ? null : Number(row.price),
          quantity: row.quantity === '' ? null : Number(row.quantity),
          fee: row.fee === '' ? 0 : Number(row.fee),
        })),
      });
      if (result.status === 'rejected') {
        setError('有 ' + (result.rejected?.length || 0) + ' 行未通过校验，已全部拒绝，没有任何记录写入。');
        setStatus('');
      } else {
        setStatus('已写入 ' + result.inserted_count + ' 行，跳过重复 ' + (result.skipped?.length || 0) + ' 行。');
        setUpload(null);
        setRows([]);
        onImported();
      }
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
      await api.addManualFill({
        ...row,
        price: row.price === '' ? null : Number(row.price),
        quantity: row.quantity === '' ? null : Number(row.quantity),
        fee: row.fee === '' ? 0 : Number(row.fee),
      });
      setStatus('已手工补录 1 笔。');
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
      <Panel title="导入交割记录">
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
          {busy ? '正在本地解析…' : '把券商成交截图、交割单 PDF、CSV 拖到这里，或点击选择文件'}
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            原文件只保存在本机，永不上传。识别在本机完成。
          </div>
          <input
            ref={inputRef}
            type="file"
            style={{ display: 'none' }}
            accept=".csv,.tsv,.txt,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
              event.target.value = '';
            }}
          />
        </div>
        {status ? <div className="muted" style={{ marginTop: 10 }}>{status}</div> : null}
        {error ? <div className="banner-error" style={{ marginTop: 10 }}><Banner>{error}</Banner></div> : null}
        {upload && upload.extraction.status === 'engine_missing' ? (
          <div style={{ marginTop: 10 }}>
            <Banner>
              本机还没有安装本地 OCR 组件，无法识别截图或扫描 PDF。安装后即可离线识别：
              <code style={{ marginLeft: 6 }}>pip install "smartmoney-cub-harness[ocr]"</code>
            </Banner>
          </div>
        ) : null}
      </Panel>

      {rows.length > 0 ? (
        <Panel
          title={'校对识别结果（' + rows.length + ' 行）'}
          actions={<button className="primary" onClick={submit} disabled={busy}>确认导入</button>}
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
  const update = (index: number, key: keyof DraftRow, value: string) => {
    onChange(rows.map((row, position) => (position === index ? { ...row, [key]: value } : row)));
  };
  const candidates = extraction?.rows || [];
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th>日期</th><th>时间</th><th>代码</th><th>名称</th><th>方向</th>
            <th>价格</th><th>数量</th><th>费用</th><th>置信度</th><th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const confidence = candidates[index]?.field_confidence || {};
            const lowest = Math.min(...Object.values(confidence).concat(1));
            return (
              <tr key={index}>
                <td><input style={{ width: 110 }} value={row.trade_date} onChange={(event) => update(index, 'trade_date', event.target.value)} /></td>
                <td><input style={{ width: 88 }} value={row.trade_time} onChange={(event) => update(index, 'trade_time', event.target.value)} /></td>
                <td><input style={{ width: 84 }} value={row.symbol} onChange={(event) => update(index, 'symbol', event.target.value)} /></td>
                <td><input style={{ width: 96 }} value={row.name} onChange={(event) => update(index, 'name', event.target.value)} /></td>
                <td>
                  <select value={row.side} onChange={(event) => update(index, 'side', event.target.value)}>
                    <option value="BUY">买入</option>
                    <option value="SELL">卖出</option>
                  </select>
                </td>
                <td><input style={{ width: 84 }} value={row.price} onChange={(event) => update(index, 'price', event.target.value)} /></td>
                <td><input style={{ width: 92 }} value={row.quantity} onChange={(event) => update(index, 'quantity', event.target.value)} /></td>
                <td><input style={{ width: 72 }} value={row.fee} onChange={(event) => update(index, 'fee', event.target.value)} /></td>
                <td>
                  {lowest >= 0.85 ? <span className="badge ok">高</span>
                    : lowest >= 0.6 ? <span className="badge warn">中</span>
                      : <span className="badge error">低</span>}
                </td>
                <td>
                  <button className="ghost" onClick={() => onChange(rows.filter((_, position) => position !== index))}>删除</button>
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
  const [row, setRow] = useState<DraftRow>({ ...EMPTY_ROW });
  const update = (key: keyof DraftRow, value: string) => setRow((prev) => ({ ...prev, [key]: value }));
  return (
    <Panel title="手工补录一笔">
      <div className="row">
        <div className="field"><label>日期</label><input value={row.trade_date} onChange={(event) => update('trade_date', event.target.value)} placeholder="2026-09-01" /></div>
        <div className="field"><label>时间</label><input value={row.trade_time} onChange={(event) => update('trade_time', event.target.value)} placeholder="09:35:00" /></div>
        <div className="field"><label>代码</label><input style={{ width: 90 }} value={row.symbol} onChange={(event) => update('symbol', event.target.value)} /></div>
        <div className="field"><label>名称</label><input value={row.name} onChange={(event) => update('name', event.target.value)} /></div>
        <div className="field">
          <label>方向</label>
          <select value={row.side} onChange={(event) => update('side', event.target.value)}>
            <option value="BUY">买入</option><option value="SELL">卖出</option>
          </select>
        </div>
        <div className="field"><label>价格</label><input style={{ width: 90 }} value={row.price} onChange={(event) => update('price', event.target.value)} /></div>
        <div className="field"><label>数量</label><input style={{ width: 100 }} value={row.quantity} onChange={(event) => update('quantity', event.target.value)} /></div>
        <div className="field"><label>费用</label><input style={{ width: 80 }} value={row.fee} onChange={(event) => update('fee', event.target.value)} /></div>
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            if (await onSubmit(row)) setRow({ ...EMPTY_ROW });
          }}
        >
          补录
        </button>
      </div>
    </Panel>
  );
}

