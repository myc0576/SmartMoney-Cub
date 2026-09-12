import React, { useState, useEffect } from 'react';
import { Database, FileText, CheckCircle2, RotateCcw, ShieldCheck } from 'lucide-react';
import { api } from '../api';

export const WorkspaceView: React.FC = () => {
  const [summary, setSummary] = useState<any>(null);
  const [cases, setCases] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [sumRes, casesRes] = await Promise.all([
        api.getWorkspaceSummary(),
        api.getWorkspaceCases(actionFilter ? { action: actionFilter } : {}),
      ]);
      setSummary(sumRes.summary || null);
      setCases(casesRes.cases || []);
    } catch (e: any) {
      console.error('Failed to load workspace data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [actionFilter]);

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* 顶部总览统计 */}
      <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3 shadow-sm">
        <div className="flex items-center justify-between pb-2 border-b border-[#2a2e39]/60">
          <div className="flex items-center gap-2">
            <Database className="text-[#2962ff]" size={16} />
            <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
              本地 SQLite 决策与复盘数据集 (Review Workspace)
            </h3>
          </div>
          <button
            onClick={loadData}
            className="text-[11px] text-[#787b86] hover:text-[#d1d4dc] flex items-center gap-1"
          >
            <RotateCcw size={11} />
            <span>刷新</span>
          </button>
        </div>

        {summary && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
            <div className="bg-[#131722] p-3 rounded-lg border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86]">总决策案例 (Cases)</div>
              <div className="text-base font-bold text-[#f0f3fa] mt-1">{summary.case_count} 笔</div>
            </div>
            <div className="bg-[#131722] p-3 rounded-lg border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86]">结果追踪 (Outcomes)</div>
              <div className="text-base font-bold text-[#f0f3fa] mt-1">{summary.outcome_count} 笔</div>
            </div>
            <div className="bg-[#131722] p-3 rounded-lg border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86]">插件证据包 (Evidence)</div>
              <div className="text-base font-bold text-emerald-400 mt-1">{summary.evidence_count} 份</div>
            </div>
            <div className="bg-[#131722] p-3 rounded-lg border border-[#2a2e39]">
              <div className="text-[10px] text-[#787b86]">现役铁律 (Champions)</div>
              <div className="text-base font-bold text-amber-300 mt-1">{summary.champion_rule_count} 条</div>
            </div>
          </div>
        )}

        {summary?.statistical_limits && (
          <p className="text-[11px] text-[#787b86] bg-[#131722] p-2.5 rounded border border-[#2a2e39]/60 leading-relaxed">
            <strong className="text-amber-300">统计学诚信声明: </strong>
            {summary.statistical_limits}
          </p>
        )}
      </div>

      {/* 案例列表与筛选 */}
      <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <FileText size={14} className="text-[#2962ff]" />
            <h4 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
              决策案例记录明细 ({cases.length})
            </h4>
          </div>

          {/* Action 筛选 */}
          <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded-lg border border-[#363a45] text-xs">
            {['', 'ALERT', 'IMPORTED', 'AVOID', 'SILENT'].map((act) => (
              <button
                key={act}
                onClick={() => setActionFilter(act)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                  actionFilter === act
                    ? 'bg-[#2962ff] text-white shadow'
                    : 'text-[#787b86] hover:text-[#d1d4dc]'
                }`}
              >
                {act || '全部动作'}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="w-full text-left text-xs text-[#d1d4dc]">
            <thead className="bg-[#131722] text-[#787b86] border-b border-[#2a2e39] text-[11px] font-mono sticky top-0">
              <tr>
                <th className="py-2.5 px-3">案例 ID</th>
                <th className="py-2.5 px-3">标的代码</th>
                <th className="py-2.5 px-3">决策动作 (Action)</th>
                <th className="py-2.5 px-3">决策时间 (Decision Time)</th>
                <th className="py-2.5 px-3">计划止损价</th>
                <th className="py-2.5 px-3">开仓理由与假设</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2e39]/60 font-mono text-[11px]">
              {cases.length > 0 ? (
                cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-[#2a2e39]/30 transition-colors">
                    <td className="py-2 px-3 text-[#2962ff] font-bold">{c.case_id}</td>
                    <td className="py-2 px-3 text-[#f0f3fa]">{c.symbol}</td>
                    <td className="py-2 px-3">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        c.action === 'ALERT'
                          ? 'bg-amber-950 text-amber-400 border border-amber-800'
                          : c.action === 'IMPORTED'
                          ? 'bg-slate-800 text-slate-300 border border-slate-700'
                          : c.action === 'AVOID'
                          ? 'bg-purple-950 text-purple-400 border border-purple-800'
                          : 'bg-[#131722] text-[#787b86]'
                      }`}>
                        {c.action}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-[#787b86]">{c.decision_time?.slice(0, 16) || '-'}</td>
                    <td className="py-2 px-3">
                      {c.invalidation_price ? `¥${c.invalidation_price}` : '-'}
                    </td>
                    <td className="py-2 px-3 font-sans text-[#787b86] truncate max-w-xs" title={c.thesis}>
                      {c.thesis || '-'}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[#787b86] font-sans">
                    暂无案例记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
