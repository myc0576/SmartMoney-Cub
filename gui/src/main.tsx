import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './tokens.css';
import './styles.css';

// tokens.css is imported first on purpose: it defines the `--color-*` semantic
// palette, and styles.css expresses the existing layout in terms of those
// tokens. Reversing the order would leave the aliases pointing at nothing for
// the first paint.
const container = document.getElementById('root');
if (!container) {
  throw new Error('root container is missing');
}
createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
