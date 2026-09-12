import React from 'react';
import { Compass, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { RegimeInfo } from '../types';

interface RegimeViewProps {
  activeRegime: string;
  regimePhases: Record<string, RegimeInfo>;
  onSelectRegime: (name: string) => void;
}

export const RegimeView: React.FC<RegimeViewProps> = ({
  activeRegime,
  regimePhases,
  onSelectRegime,
}) => {
  const currentInfo = regimePhases[activeRegime] || regimePhases['生长'];

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* 易经情绪五阶段罗盘卡片组 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {Object.entries(regimePhases).map(([name, phase]) => {
          const isSelected = activeRegime === name;
          return (
            <div
              key={name}
              onClick={() => onSelectRegime(name)}
              className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col justify-between select-none ${
                isSelected
                  ? 'bg-[#1e222d] border-[#2962ff] shadow-lg shadow-[#2962ff]/10 ring-1 ring-[#2962ff]'
                  : 'bg-[#1e222d]/60 border-[#2a2e39] hover:border-[#363a45]'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#f0f3fa] flex items-center gap-1.5">
                  <Compass size={13} className={isSelected ? 'text-[#2962ff]' : 'text-[#787b86]'} />
                  {phase.title.split(' · ')[0]}
                </span>
                <span className="text-[10px] font-mono text-[#787b86]">{phase.stage_order}/5</span>
              </div>
              <div className="mt-3">
                <div className="text-sm font-bold text-[#d1d4dc]">{phase.title.split(' · ')[1] || phase.name}</div>
                <div className="text-[11px] text-[#787b86] mt-1 font-mono">
                  建议仓位: {phase.recommended_position.split(' ')[0]}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 当前活跃周期的深度操盘罗盘详情 */}
      <div className="bg-[#1e222d] p-5 rounded-xl border border-[#2a2e39] space-y-4 shadow-sm">
        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 pb-4 border-b border-[#2a2e39]">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[#f0f3fa]">
                当前情绪阶段: 【{currentInfo.name}】 {currentInfo.title}
              </h2>
              <span className="text-xs px-2 py-0.5 rounded bg-[#131722] text-[#2962ff] font-mono border border-[#363a45]">
                阶段 {currentInfo.stage_order} / 5
              </span>
            </div>
            <p className="text-xs text-[#787b86] mt-1.5 leading-relaxed max-w-3xl">
              {currentInfo.description}
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono shrink-0">
            <div className="bg-[#131722] p-2 rounded-lg border border-[#2a2e39]">
              <div className="text-[#787b86] text-[10px]">梯队高度空间</div>
              <div className="font-bold text-[#f0f3fa] mt-0.5">{currentInfo.ladder_height_range}</div>
            </div>
            <div className="bg-[#131722] p-2 rounded-lg border border-[#2a2e39]">
              <div className="text-[#787b86] text-[10px]">建议行动基调</div>
              <div className="font-bold text-amber-400 mt-0.5">{currentInfo.action_stance}</div>
            </div>
          </div>
        </div>

        {/* 心法箴言 Maxims */}
        <div className="p-3.5 rounded-lg bg-[#131722] border border-[#2a2e39] space-y-1.5">
          <div className="text-xs font-bold text-[#2962ff] flex items-center gap-1.5">
            <ShieldCheck size={14} />
            <span>游资周期操盘箴言 (Maxims):</span>
          </div>
          <ul className="space-y-1 text-xs text-[#d1d4dc] pl-4 list-disc marker:text-[#2962ff]">
            {currentInfo.maxims.map((m, idx) => (
              <li key={idx} className="leading-relaxed">{m}</li>
            ))}
          </ul>
        </div>

        {/* 允许战法 (Allowed) vs 绝禁动作 (Forbidden) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {/* 允许模式 */}
          <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
              <CheckCircle2 size={14} />
              <span>本阶段允许开仓模式 (Allowed Setups)</span>
            </div>
            <ul className="space-y-1.5 text-xs text-emerald-200/80">
              {currentInfo.allowed_setups.map((s, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-emerald-400 font-bold">&check;</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* 违规禁绝 */}
          <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-500/30 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-rose-400">
              <XCircle size={14} />
              <span>本阶段绝禁违规动作 (Forbidden Actions)</span>
            </div>
            <ul className="space-y-1.5 text-xs text-rose-200/80">
              {currentInfo.forbidden_actions.map((f, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-rose-400 font-bold">&times;</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};
