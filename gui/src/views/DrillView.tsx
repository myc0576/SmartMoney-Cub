import { ReplayView } from './ReplayView';

/** Practice stays isolated from the journal; accounts live in Connections. */
export function DrillView({ scheme }: { scheme: 'cn' | 'intl' }) {
  return <ReplayView scheme={scheme} />;
}
