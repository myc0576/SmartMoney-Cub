// The brand mark is imported as a module rather than referenced as a public URL
// so Vite fingerprints it and rewrites the path for the prefix the interface may
// be served under. The image on screen is the 512px source, scaled down to the
// sidebar slot so it stays crisp on a dense display; the 32px PNG in public/ is
// the browser-tab icon.
//
// smartmoney-cub-mark.png here is a copy of the published assets/ file of the
// same name. Bundler input has to live under the Vite root to be fingerprinted,
// and reaching outside gui/ would mean aliasing an out-of-root path, which costs
// more than it saves for a file this small. Re-copy it if the artwork changes.
import markUrl from './smartmoney-cub-mark.png';

export const BRAND_MARK_SRC = markUrl;
