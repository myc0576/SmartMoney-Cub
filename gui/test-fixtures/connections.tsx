// Development-only fixture. Not an entry point of the production Vite build.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { AgentConnections, JevConnection } from '../src/views/ConnectionSettings';
import { AssistantPanel } from '../src/components/AssistantPanel';
import type { Meta } from '../src/types';
import '../src/tokens.css';
import '../src/styles.css';

const meta = {
  default_provider: 'toy', default_model: 'toy-model', default_reasoning: 'off',
  providers: [{ provider_id: 'toy', label: 'Toy Provider', protocol: 'openai-chat', routable: true,
    models: [{ id: 'toy-model', label: 'Toy Model', reasoning_efforts: ['off'] }] }],
} as unknown as Meta;
const view = new URLSearchParams(location.search).get('view');
createRoot(document.getElementById('root')!).render(
  <div style={{ display: 'flex', minHeight: '90vh', maxWidth: 900, padding: 20 }}>
    {view === 'assistant' ? <AssistantPanel meta={meta} context={{}} />
      : view === 'agents' ? <AgentConnections /> : <JevConnection />}
  </div>,
);
