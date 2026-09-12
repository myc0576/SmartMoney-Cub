import { AppDataResponse, PluginCatalogEntry, PluginItem, ProfileItem } from './types';

export const api = {
  async getData(): Promise<AppDataResponse> {
    const res = await fetch('/api/data');
    if (!res.ok) throw new Error(`Failed to fetch data: ${res.statusText}`);
    return res.json();
  },

  async setRegime(regime: string) {
    const res = await fetch('/api/set_regime', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ regime }),
    });
    return res.json();
  },

  async uploadCsv(csvContent: string) {
    const res = await fetch('/api/upload_csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: csvContent }),
    });
    return res.json();
  },

  async resetDemo() {
    const res = await fetch('/api/reset_demo', { method: 'POST' });
    return res.json();
  },

  async addRule(ruleData: any) {
    const res = await fetch('/api/add_rule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ruleData),
    });
    return res.json();
  },

  async requestPromotion(ruleId: string, confirm: boolean = false, note: string = '') {
    const res = await fetch('/api/request_promotion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rule_id: ruleId, confirm, note }),
    });
    return res.json();
  },

  async getPlugins(): Promise<{ plugins: PluginItem[]; rejected: any[] }> {
    const res = await fetch('/api/plugins/list');
    return res.json();
  },

  async togglePlugin(pluginId: string, enabled: boolean) {
    const res = await fetch('/api/plugins/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plugin_id: pluginId, enabled }),
    });
    return res.json();
  },

  async installPlugin(source: string) {
    const res = await fetch('/api/plugins/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source }),
    });
    return res.json();
  },

  async getPluginCatalog(): Promise<{ entries: PluginCatalogEntry[]; by_level: Record<string, PluginCatalogEntry[]> }> {
    const res = await fetch('/api/plugins/catalog');
    return res.json();
  },

  async getProfiles(): Promise<{ active_profile: string; profiles: Record<string, ProfileItem> }> {
    const res = await fetch('/api/profiles');
    return res.json();
  },

  async switchProfile(profile: string) {
    const res = await fetch('/api/profiles/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile }),
    });
    return res.json();
  },

  async getWorkspaceSummary() {
    const res = await fetch('/api/workspace/summary');
    return res.json();
  },

  async getWorkspaceCases(filters: { action?: string; symbol?: string; regime?: string } = {}) {
    const query = new URLSearchParams();
    if (filters.action) query.set('action', filters.action);
    if (filters.symbol) query.set('symbol', filters.symbol);
    if (filters.regime) query.set('regime', filters.regime);
    const res = await fetch(`/api/workspace/cases?${query.toString()}`);
    return res.json();
  },

  async generateSharePack(title?: string, policy?: any) {
    const res = await fetch('/api/share_pack/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, policy }),
    });
    return res.json();
  },
};
