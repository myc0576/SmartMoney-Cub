import React, { useState } from 'react';
import { ShieldCheck, Flame, ArrowUpRight, Lock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { RuleItem } from '../types';

interface RulesViewProps {
  champions: RuleItem[];
  challengers: RuleItem[];
  onRequestPromotion: (ruleId: string) => void;
}

export const RulesView: React.FC<RulesViewProps> = ({
  champions,
  challengers,
  onRequestPromotion,
}) => {
  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-6">
      {/* 规则进化说明条 */}
      <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] flex items-start gap-3">
        <ShieldCheck className="text-emerald-400 shrink-0 mt-0.5" size={18} />
        <div className="text-xs">
          <div className="font-bold text-[#f0f3fa]">
            严格遵循 Challenger &rarr; Champion 双轨进化与人工晋级门禁
          </div>
          <p className="text-[#787b86] mt-1 leading-relaxed">
            任何来自复盘提炼或外部分析器的规则，初始只能进入 Challenger 观察池进行实战样本检验（要求 &ge; 20 笔样本，且无未来数据泄露）。系统严禁任何自动直接改写 Champion 铁律的行为，晋级必须经过两阶段显式人工确认。
          </p>
        </div>
      </div>

      {/* 现役核心铁律库 Champion Rules */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
            <Lock size={13} className="text-emerald-400" />
            <span>Champion 现役核心铁律库 ({champions.length})</span>
          </h3>
          <span className="text-[11px] text-[#787b86]">实战最高优先级防线</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {champions.map((rule) => (
            <div
              key={rule.rule_id}
              className="bg-[#1e222d] p-4 rounded-xl border border-emerald-500/30 flex flex-col justify-between space-y-3 shadow-sm"
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800/60">
                    {rule.rule_id}
                  </span>
                  <span className="text-[10px] text-emerald-300 flex items-center gap-1">
                    <CheckCircle2 size={11} /> 现役铁律
                  </span>
                </div>
                <div className="text-sm font-bold text-[#f0f3fa] leading-snug">
                  {rule.title}
                </div>
                <p className="text-xs text-[#787b86] leading-relaxed">
                  {rule.description || rule.condition}
                </p>
              </div>

              <div className="pt-2 border-t border-[#2a2e39]/60 flex justify-between items-center text-[11px] text-[#787b86] font-mono">
                <span>实战样本: <strong className="text-[#d1d4dc]">{rule.sample_count || 20} 次</strong></span>
                <span className="text-[10px] text-[#50535e]">{rule.promoted_at || '已确立'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 观察候选防御规则池 Challenger Rules */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
            <Flame size={13} className="text-amber-400" />
            <span>Challenger 观察候选规则池 ({challengers.length})</span>
          </h3>
          <span className="text-[11px] text-[#787b86]">门禁要求: &ge; 20 笔实战样本</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {challengers.map((rule) => {
            const tested = rule.tested_samples || 1;
            const target = rule.target_samples || 20;
            const progress = Math.min(100, Math.round((tested / target) * 100));
            const isEligible = tested >= target;

            return (
              <div
                key={rule.rule_id}
                className="bg-[#1e222d] p-4 rounded-xl border border-amber-500/30 flex flex-col justify-between space-y-3 shadow-sm"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono font-bold text-amber-400 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800/60">
                      {rule.rule_id}
                    </span>
                    <span className="text-[10px] text-amber-300 font-medium">
                      考察中 ({progress}%)
                    </span>
                  </div>
                  <div className="text-sm font-bold text-[#f0f3fa] leading-snug">
                    {rule.title}
                  </div>
                  <p className="text-xs text-[#787b86] leading-relaxed">
                    {rule.description || rule.condition}
                  </p>

                  {/* 样本数跟踪进度条 */}
                  <div className="space-y-1 pt-1">
                    <div className="flex justify-between text-[11px] text-[#787b86] font-mono">
                      <span>样本积累进度</span>
                      <span className={isEligible ? 'text-emerald-400 font-bold' : 'text-amber-400 font-bold'}>
                        {tested} / {target} 次
                      </span>
                    </div>
                    <div className="w-full bg-[#131722] rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-1.5 rounded-full transition-all ${
                          isEligible ? 'bg-emerald-500' : 'bg-amber-500'
                        }`}
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-[#2a2e39]/60 flex justify-between items-center">
                  <span className="text-[11px] text-[#787b86] truncate max-w-[50%]">
                    {rule.source_trade ? `来源: ${rule.source_trade}` : '复盘总结提炼'}
                  </span>
                  <button
                    onClick={() => onRequestPromotion(rule.rule_id)}
                    className={`px-2.5 py-1 rounded text-xs font-medium flex items-center gap-1 transition-all ${
                      isEligible
                        ? 'bg-[#10b981]/20 hover:bg-[#10b981]/30 text-emerald-300 border border-emerald-500/40 shadow'
                        : 'bg-[#2a2e39] hover:bg-[#363a45] text-[#787b86] hover:text-[#d1d4dc] border border-[#363a45]'
                    }`}
                  >
                    <span>申请晋升 Champion</span>
                    <ArrowUpRight size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
