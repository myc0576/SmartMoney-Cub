import React, { useState } from 'react';
import { X, ShieldCheck, Download, Copy, ExternalLink, Check, AlertTriangle } from 'lucide-react';
import { api } from '../api';

interface SharePackModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SharePackModal: React.FC<SharePackModalProps> = ({ isOpen, onClose }) => {
  const [packTitle, setPackTitle] = useState('SmartMoney-Cub 游资短线复盘包');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleGenerate = async () => {
    try {
      setLoading(true);
      const res = await api.generateSharePack(packTitle);
      setResult(res);
    } catch (e: any) {
      alert('生成分享包失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyHtml = () => {
    if (!result?.html) return;
    navigator.clipboard.writeText(result.html);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!result?.html) return;
    const blob = new Blob([result.html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'share_pack.html';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePreview = () => {
    if (!result?.html) return;
    const blob = new Blob([result.html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#1e222d] border border-[#363a45] w-full max-w-xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* 头部 */}
        <div className="px-5 py-4 border-b border-[#2a2e39] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-emerald-400" />
            <h3 className="text-sm font-bold text-[#f0f3fa]">生成不可变匿名复盘分享包</h3>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded hover:bg-[#2a2e39] flex items-center justify-center text-[#787b86] hover:text-[#d1d4dc]"
          >
            <X size={16} />
          </button>
        </div>

        {/* 内容 */}
        <div className="p-5 space-y-4 overflow-y-auto text-xs">
          <p className="text-[#787b86] leading-relaxed">
            分享包为单文件离线静态 HTML，证券代码与名称已进行哈希与脱敏替换，金额粗化至千元，盘中秒级时间降为日期，严防真实账户泄露。
          </p>

          <div className="space-y-1.5">
            <label className="text-[#d1d4dc] font-medium">分享包标题</label>
            <input
              type="text"
              value={packTitle}
              onChange={(e) => setPackTitle(e.target.value)}
              className="w-full h-8 px-3 bg-[#131722] border border-[#363a45] rounded-lg text-xs text-[#d1d4dc] focus:outline-none focus:border-[#2962ff]"
            />
          </div>

          <div className="p-3 rounded-lg bg-[#131722] border border-[#2a2e39] space-y-1.5">
            <div className="font-bold text-[#2962ff]">自动脱敏与隐私降级策略:</div>
            <ul className="text-[#787b86] space-y-1 pl-4 list-disc text-[11px]">
              <li>证券代码 (Symbol): SHA-256 不可逆哈希前缀 (id-xxxx)</li>
              <li>标的名称 (Name): 自动替换为 REDACTED 掩码</li>
              <li>金额与收益 (Amount): 粗化降精度 (Coarsen to 1000)</li>
              <li>时间字段 (Time): 剥离盘中分秒，仅保留发生日期</li>
            </ul>
          </div>

          {/* 生成动作 */}
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-[#2962ff] hover:bg-[#2962ff]/90 text-white font-medium text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
          >
            {loading ? '正在生成并执行隐私审计...' : '开始生成与审计'}
          </button>

          {/* 生成结果与审计 */}
          {result && (
            <div className="p-4 rounded-xl bg-[#131722] border border-[#2a2e39] space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                    <Check size={14} />
                    <span>审计状态: {result.audit?.status?.toUpperCase()}</span>
                  </span>
                  <span className="text-[10px] text-[#787b86] font-mono">
                    检出隐私标识: {result.audit?.hit_count || 0}
                  </span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 font-mono border border-emerald-800">
                  只读离线 · 未联网上传
                </span>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-[#2a2e39]">
                <button
                  onClick={handleCopyHtml}
                  className="flex-1 py-1.5 rounded bg-[#1e222d] hover:bg-[#2a2e39] border border-[#363a45] text-[#d1d4dc] font-medium flex items-center justify-center gap-1 transition-all"
                >
                  <Copy size={12} />
                  <span>{copied ? '已复制 HTML' : '复制 HTML'}</span>
                </button>
                <button
                  onClick={handleDownload}
                  className="flex-1 py-1.5 rounded bg-[#1e222d] hover:bg-[#2a2e39] border border-[#363a45] text-[#d1d4dc] font-medium flex items-center justify-center gap-1 transition-all"
                >
                  <Download size={12} />
                  <span>下载 .html 文件</span>
                </button>
                <button
                  onClick={handlePreview}
                  className="py-1.5 px-3 rounded bg-[#2962ff]/20 hover:bg-[#2962ff]/30 text-[#2962ff] border border-[#2962ff]/40 font-medium flex items-center justify-center gap-1 transition-all"
                >
                  <ExternalLink size={12} />
                  <span>预览</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
