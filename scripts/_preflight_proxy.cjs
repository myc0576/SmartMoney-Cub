/* The shipped nginx rules, applied by a stand-in.
 *
 * scripts/preflight.py drives this so the deployment's own routing is executed
 * rather than read: the /trader prefix is stripped, the access token is injected
 * on the way through (a browser cannot send that header itself), and the
 * longest matching prefix wins, exactly as deploy/nginx.conf specifies.
 *
 * It is a stand-in, not nginx. On a host with nginx installed, run the real
 * thing; this exists so the path is executed on a machine that has none.
 *
 * Usage: node _preflight_proxy.cjs <appBase> <port> <token> [prefix]
 */
const http = require('http');
const APP = process.argv[2];
const PORT = parseInt(process.argv[3], 10);
const TOKEN = process.argv[4];
const PREFIX = process.argv[5] || '/trader';

function proxy(req, res, targetPath) {
  const query = req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : '';
  const url = new URL(targetPath + query, APP);
  const headers = Object.assign({}, req.headers, { host: url.host, 'x-smcub-token': TOKEN });
  delete headers['accept-encoding'];
  const up = http.request(url, { method: req.method, headers }, (r) => {
    res.writeHead(r.statusCode, r.headers);
    r.pipe(res);
  });
  up.on('error', (e) => { res.writeHead(502); res.end('proxy error: ' + e.message); });
  req.pipe(up);
}

http.createServer((req, res) => {
  const p = req.url.split('?')[0];
  if (p === PREFIX) { res.writeHead(301, { Location: PREFIX + '/' }); res.end(); return; }
  if (p.startsWith(PREFIX + '/')) {
    /* Longest prefix first, which is the rule nginx applies and the reason the
     * two API blocks below work. */
    if (p.startsWith(PREFIX + '/api/trader/')) {
      proxy(req, res, p.slice(PREFIX.length));
      return;
    }
    /* The trust boundary. Anything else under the API prefix is the local
     * single-user review workbench: it resolves no tenant identity and reads the
     * container's own shared state directory, so publishing it shows every user
     * the same data. The shipped config closes this by default, and the stand-in
     * reproduces that rather than modelling a wider surface than the deployment
     * actually has -- a stand-in that is more permissive than the config proves
     * nothing about the config. */
    if (p.startsWith(PREFIX + '/api/')) {
      res.writeHead(403, { 'Content-Type': 'text/plain' });
      res.end('trust boundary: the workbench API is not published');
      return;
    }
    proxy(req, res, p.slice(PREFIX.length));
    return;
  }
  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('default location: 404');
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write('preflight proxy on ' + PORT + PREFIX + '/\n');
});
