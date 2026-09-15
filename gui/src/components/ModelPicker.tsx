import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyStatus, ModelEntry, ProviderView, ReasoningEffort } from '../types';

// The model seat: one control that switches provider, model, and reasoning
// effort for the current session.
//
// The layout follows DSH's model selection. One session-level directory, two
// levels: picking a model moves to the effort stage, and that stage offers only
// the levels the exact model advertises. Models stay grouped by provider, and
// every effort row carries a human label plus a one-line explanation, because a
// bare wire enum like "xhigh" tells the user nothing about what it buys.

const EFFORT_LABELS: Record<string, string> = {
  off: '不思考',
  low: '低',
  medium: '中',
  high: '高',
  max: '最大',
};

export function effortLabel(effort: string): string {
  return EFFORT_LABELS[effort] || effort;
}

export function findModel(providers: ProviderView[], providerId: string, modelId: string): ModelEntry | null {
  const provider = providers.find((item) => item.provider_id === providerId);
  return provider?.models.find((item) => item.id === modelId) || null;
}

interface Selection {
  provider_id: string;
  model: string;
  reasoning: string;
}

/** One row of the effort stage, resolved from the model or mapped from its ids. */
interface EffortRow {
  level: string;
  name: string;
  desc?: string;
  isDefault: boolean;
}

const PROVIDER_KEY_LABELS: Record<KeyStatus, string> = {
  configured: '密钥已配置',
  missing: '缺少密钥',
  unknown: '密钥状态未知',
};

/** How many reasoning levels a model advertises, whichever source is filled in. */
function effortCount(model: ModelEntry | null): number {
  if (!model) return 0;
  if (model.effort_details && model.effort_details.length > 0) return model.effort_details.length;
  return (model.reasoning_efforts || []).length;
}

/**
 * The effort rows for one model.
 *
 * The rich rows come first, since they carry the description. Only when the
 * model has no effort_details does the row fall back to the published ids run
 * through effortLabel(), which is the best name available for a bare enum.
 */
function effortRows(model: ModelEntry | null): EffortRow[] {
  if (!model) return [];
  const fallback = model.default_effort || model.reasoning_efforts?.[0] || '';
  if (model.effort_details && model.effort_details.length > 0) {
    return model.effort_details.map((detail: ReasoningEffort) => ({
      level: detail.level,
      name: detail.label || effortLabel(detail.level),
      desc: detail.description,
      isDefault: Boolean(detail.is_default) || detail.level === fallback,
    }));
  }
  return (model.reasoning_efforts || []).map((level) => ({
    level,
    name: effortLabel(level),
    isDefault: level === fallback,
  }));
}

/** "272K" / "1.0M" - enough to compare models at a glance without a full count. */
function contextHint(tokens?: number): string | null {
  if (!tokens || tokens <= 0) return null;
  if (tokens >= 1_000_000) return (tokens / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (tokens >= 1000) return Math.round(tokens / 1000) + 'K';
  return String(tokens);
}

export function ModelPicker({
  providers,
  selection,
  onSelect,
  disabled,
}: {
  providers: ProviderView[];
  selection: Selection;
  onSelect: (next: Selection) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [stage, setStage] = useState<'model' | 'effort'>('model');
  // Which provider's key the user is inspecting. The dot explains itself on
  // click so a red or hollow dot is never left to guesswork.
  const [keyNote, setKeyNote] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Escape closes the menu from anywhere inside it, including the search box.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setStage('model');
        setQuery('');
        setKeyNote(null);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        setStage('model');
        setQuery('');
        setKeyNote(null);
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return providers
      .map((provider) => ({
        provider,
        models: provider.models.filter(
          (model) =>
            !needle ||
            model.id.toLowerCase().includes(needle) ||
            (model.label || '').toLowerCase().includes(needle) ||
            (model.description || '').toLowerCase().includes(needle) ||
            provider.label.toLowerCase().includes(needle),
        ),
      }))
      // A provider whose model lookup failed keeps its group so the reason
      // renders inline, even though there are no rows to list under it. Every
      // other provider still lists its own models beside it.
      .filter(
        (group) =>
          group.models.length > 0 ||
          Boolean(group.provider.models_error && (!needle || group.provider.label.toLowerCase().includes(needle))),
      );
  }, [providers, query]);

  const current = findModel(providers, selection.provider_id, selection.model);
  const currentProvider = providers.find((item) => item.provider_id === selection.provider_id);
  const rows = effortRows(current);
  // Whether the current selection is still a row in the published directory.
  // This is deliberately narrower than "is the route usable": DSH falls back
  // to the generic label only when the provider/model pair is absent from the
  // directory. A provider that is present but merely has no key yet is still a
  // real choice, so the seat keeps naming it.
  const listed = Boolean(current && currentProvider);

  // A selection that is not in the published list must not block the composer,
  // so the trigger reports the fallback label instead of fabricating a stale row.
  // The previous selection is what the menu renders for its active state.
  const triggerLabel = listed ? current!.label || current!.id : '选择模型';

  const choose = (providerId: string, model: ModelEntry) => {
    onSelect({
      provider_id: providerId,
      model: model.id,
      // Selecting a model applies that model's default effort; the effort row
      // then narrows to what that exact model advertises.
      reasoning: model.default_effort || model.reasoning_efforts?.[0] || 'off',
    });
    setQuery('');
    if (effortCount(model) > 1) {
      setStage('effort');
    } else {
      setOpen(false);
      setStage('model');
    }
  };

  const close = () => {
    setOpen(false);
    setStage('model');
    setQuery('');
    setKeyNote(null);
  };

  return (
    <div className="picker" ref={rootRef}>
      <button
        className={'picker-trigger' + (open ? ' open' : '')}
        onClick={() => {
          const next = !open;
          setOpen(next);
          setStage('model');
          setKeyNote(null);
        }}
        disabled={disabled}
        title="切换 Provider、模型与推理强度"
      >
        <span className="picker-label">{triggerLabel}</span>
        {listed && rows.length > 0 && selection.reasoning && selection.reasoning !== 'off' ? (
          <span className="picker-effort">{effortLabel(selection.reasoning)}</span>
        ) : null}
        <span className="picker-caret">▾</span>
      </button>

      {open ? (
        <div className="picker-menu" role="dialog" aria-label="选择模型">
          {stage === 'model' ? (
            <>
              <div className="picker-head">
                <input
                  autoFocus
                  className="picker-search"
                  placeholder="搜索模型、Provider 或说明"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
              <div className="picker-body">
                {providers.length === 0 ? (
                  <div className="picker-empty">
                    目录还没有加载。到「设置 → 模型」添加 Provider。
                    {selection.model ? ' 当前会话仍沿用「' + selection.model + '」。' : ''}
                  </div>
                ) : null}
                {providers.length > 0 && groups.length === 0 ? (
                  <div className="picker-empty">没有匹配的模型。换个关键词，或到「设置 → 模型」添加 Provider。</div>
                ) : null}
                {keyNote ? <div className="picker-empty">{keyNote}</div> : null}
                {groups.map((group) => {
                  const provider = group.provider;
                  const status: KeyStatus =
                    provider.key_status || (provider.has_key ? 'configured' : 'unknown');
                  return (
                    <div key={provider.provider_id}>
                      <div className="picker-group">
                        <span>{provider.label}</span>
                        <span className="picker-group-id">{provider.provider_id}</span>
                        <span
                          className={
                            'key-dot' +
                            (status === 'configured' ? ' ok' : status === 'missing' ? ' error' : ' unknown')
                          }
                          title={PROVIDER_KEY_LABELS[status]}
                          role="button"
                          tabIndex={0}
                          onClick={() => setKeyNote(provider.label + ' · ' + PROVIDER_KEY_LABELS[status])}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              setKeyNote(provider.label + ' · ' + PROVIDER_KEY_LABELS[status]);
                            }
                          }}
                        />
                        {provider.is_custom ? <span className="tag">自定义</span> : null}
                        {/* A route that cannot serve a turn right now is labelled, not
                            hidden: the model stays selectable so the seat never locks. */}
                        {provider.routable === false ? <span className="tag warn">未就绪</span> : null}
                      </div>
                      {provider.models_error ? (
                        <div className="picker-empty">
                          模型目录拉取失败：{provider.models_error}
                        </div>
                      ) : null}
                      {provider.models.length === 0 && !provider.models_error ? (
                        <div className="picker-empty">这个 Provider 还没有公布模型。</div>
                      ) : null}
                      {group.models.map((model) => {
                        const ctx = contextHint(model.context_window);
                        const active =
                          model.id === selection.model && provider.provider_id === selection.provider_id;
                        return (
                          <button
                            key={model.id}
                            className={'picker-item model-row' + (active ? ' active' : '') + (model.stale ? ' stale' : '')}
                            onClick={() => choose(provider.provider_id, model)}
                          >
                            <span className="model-row-main">
                              <span className="model-row-name">{model.label || model.id}</span>
                              <span className="model-row-sub">
                                {model.id}
                                {ctx ? ' · 上下文 ' + ctx : ''}
                              </span>
                            </span>
                            <span className="model-row-tags">
                              {effortCount(model) > 1 ? <span className="tag accent">可调强度</span> : null}
                              {model.stale ? <span className="tag warn">已下架</span> : null}
                              {model.verified === false ? <span className="tag">未校验</span> : null}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
              <div className="picker-foot">
                <button className="ghost" onClick={close}>关闭</button>
              </div>
            </>
          ) : (
            <>
              <div className="picker-head">
                <button className="picker-back" onClick={() => setStage('model')} title="返回模型列表">
                  ←
                </button>
                <span className="picker-title">推理强度</span>
              </div>
              <div className="picker-body">
                {current ? (
                  <div className="picker-group">
                    <span>{current.label || current.id}</span>
                    <span className="picker-group-id">{current.id}</span>
                  </div>
                ) : (
                  <div className="picker-empty">当前模型不在已公布目录中，下面列出的是它声明的推理强度。</div>
                )}
                {rows.map((row) => (
                  <button
                    key={row.level}
                    className={'picker-item effort-row' + (row.level === selection.reasoning ? ' active' : '')}
                    onClick={() => {
                      onSelect({ provider_id: selection.provider_id, model: selection.model, reasoning: row.level });
                      close();
                    }}
                  >
                    <span className="effort-name">
                      {row.name}
                      {row.isDefault ? <span className="tag" style={{ marginLeft: 6 }}>默认</span> : null}
                    </span>
                    {/* The description is the point of this stage: it says what the
                        level buys instead of printing a bare wire enum. */}
                    {row.desc ? <span className="effort-desc">{row.desc}</span> : null}
                  </button>
                ))}
                {rows.length === 0 ? (
                  <div className="picker-empty">
                    这个模型没有声明推理强度，沿用当前设置即可。
                  </div>
                ) : null}
              </div>
              <div className="picker-foot">
                <button className="ghost" onClick={close}>关闭</button>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
