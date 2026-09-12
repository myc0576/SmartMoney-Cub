import { useEffect, useState } from 'react';
import { api } from '../api';
import { Empty, Panel } from '../components/common';

export function PluginsView() {
  const [data, setData] = useState<Record<string, any> | null>(null);

  useEffect(() => { void api.plugins().then(setData); }, []);

  const plugins: Record<string, any>[] = (data?.plugins as Record<string, any>[]) || [];

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        插件只能读取外部数据并作为复盘证据使用。它们不能下单、不能改账户，也不能绕过脱敏。
        任何 <code>available_at</code> 晚于决策时间的证据都会判定为未来数据并拒绝。
      </div>
      <Panel title={'已发现插件（' + plugins.length + '）'}>
        {plugins.length === 0 ? <Empty text="还没有发现插件" /> : (
          <div className="scroll-x">
            <table>
              <thead><tr><th>插件</th><th>版本</th><th>状态</th><th>能力</th><th>隔离</th></tr></thead>
              <tbody>
                {plugins.map((plugin) => (
                  <tr key={plugin.plugin_id}>
                    <td>{plugin.plugin_id}</td>
                    <td className="muted">{plugin.version || '—'}</td>
                    <td>{String(plugin.state || '—')}</td>
                    <td className="muted" style={{ whiteSpace: 'normal' }}>{(plugin.capabilities || []).join(', ') || '—'}</td>
                    <td className="muted">{plugin.isolation || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {data?.error ? <Panel title="插件子系统信息"><div className="muted">{String(data.error)}</div></Panel> : null}
    </div>
  );
}

