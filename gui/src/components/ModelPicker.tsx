import { useEffect, useMemo, useRef, useState } from 'react';
import type { ModelEntry, ProviderView } from '../types';

// The model seat: one control that switches provider, model, and reasoning
// effort for the current session. Models stay grouped by provider, and the
// effort row offers only the levels the selected model actually advertises.

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
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setStage('model');
        setQuery('');
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
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
            model.label.toLowerCase().includes(needle) ||
            provider.label.toLowerCase().includes(needle),
        ),
      }))
      .filter((group) => group.models.length > 0);
  }, [providers, query]);

  const current = findModel(providers, selection.provider_id, selection.model);
  const currentProvider = providers.find((item) => item.provider_id === selection.provider_id);
  const efforts = current?.reasoning_efforts || [];
  const routable = Boolean(current && currentProvider && !currentProvider.incomplete);

  const choose = (providerId: string, model: ModelEntry) => {
    onSelect({
      provider_id: providerId,
      model: model.id,
      // Selecting a model applies that model's default effort, and the effort
      // row then narrows to what the model advertises.
      reasoning: model.default_effort || model.reasoning_efforts[0] || 'off',
    });
    if ((model.reasoning_efforts || []).length > 1) {
      setStage('effort');
    } else {
      setOpen(false);
      setQuery('');
    }
  };

  const triggerLabel = routable
    ? current!.label || current!.id
    : currentProvider
      ? '选择模型'
      : '选择模型';

  return (
    <div className="picker" ref={rootRef}>
      <button
        className={'picker-trigger' + (open ? ' open' : '')}
        onClick={() => {
          setOpen((prev) => !prev);
          setStage('model');
        }}
        disabled={disabled}
        title="切换 Provider、模型与推理强度"
      >
        <span className="picker-label">{triggerLabel}</span>
        {efforts.length > 0 && selection.reasoning && selection.reasoning !== 'off' ? (
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
                  placeholder="搜索模型或 Provider"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      setOpen(false);
                      setQuery('');
                    }
                  }}
                />
              </div>
              <div className="picker-body">
                {groups.length === 0 ? (
                  <div className="picker-empty">没有匹配的模型。到「设置 → 模型」添加 Provider。</div>
                ) : null}
                {groups.map((group) => (
                  <div key={group.provider.provider_id}>
                    <div className="picker-group">
                      {group.provider.label}
                      <span className="picker-group-id">{group.provider.provider_id}</span>
                    </div>
                    {group.models.map((model) => (
                      <button
                        key={model.id}
                        className={
                          'picker-item' +
                          (model.id === selection.model && group.provider.provider_id === selection.provider_id
                            ? ' active'
                            : '')
                        }
                        onClick={() => choose(group.provider.provider_id, model)}
                      >
                        <span>{model.label || model.id}</span>
                        {(model.reasoning_efforts || []).length > 1 ? (
                          <span className="picker-tag">可调强度</span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
              <div className="picker-foot">
                <button
                  className="ghost"
                  onClick={() => {
                    setOpen(false);
                    setStage('model');
                  }}
                >
                  关闭
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="picker-head">
                <button className="picker-back" onClick={() => setStage('model')}>←</button>
                <span className="picker-title">推理强度</span>
              </div>
              <div className="picker-body">
                <div className="picker-group">{current?.label || current?.id}</div>
                {efforts.map((effort) => (
                  <button
                    key={effort}
                    className={'picker-item' + (effort === selection.reasoning ? ' active' : '')}
                    onClick={() => {
                      onSelect({ ...selection, reasoning: effort });
                      setOpen(false);
                    }}
                  >
                    <span>{effortLabel(effort)}</span>
                    <span className="picker-tag">{effort}</span>
                  </button>
                ))}
                {efforts.length === 0 ? (
                  <div className="picker-empty">这个模型没有声明推理强度。</div>
                ) : null}
              </div>
              <div className="picker-foot">
                <button className="ghost" onClick={() => setOpen(false)}>关闭</button>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
