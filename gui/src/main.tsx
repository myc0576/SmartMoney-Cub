import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './tokens.css';
import './styles.css';
// Page-level panels introduced by the navigation convergence. Kept in their own
// sheet so the design-token pass over styles.css and these new surfaces cannot
// fight over one file.
import './panels.css';

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
