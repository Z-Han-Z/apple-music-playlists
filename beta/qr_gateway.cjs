// Minimal API Enhanced login gateway: loopback-only, no cookie cache or request logs.
'use strict';
const http = require('node:http');
const path = require('node:path');

const routes = Object.freeze({
  '/login/qr/key': 'login_qr_key',
  '/login/qr/create': 'login_qr_create',
  '/login/qr/check': 'login_qr_check',
  '/user/account': 'user_account',
});

function createGateway(sdk) {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const send = (status, body) => {
      res.statusCode = status;
      res.end(JSON.stringify(body));
    };
    const port = req.socket.localPort;
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.origin ||
        ![`127.0.0.1:${port}`, `localhost:${port}`].includes(req.headers.host)) {
      return send(403, { code: 403 });
    }
    if (req.method === 'GET' && req.url === '/health') {
      return send(200, { code: 200, login_only: true, cookies_logged: false });
    }
    const method = routes[req.url];
    if (req.method !== 'POST' || !method) return send(404, { code: 404 });
    if (req.headers['content-type'] !== 'application/x-www-form-urlencoded') {
      return send(415, { code: 415 });
    }
    try {
      let content = '';
      for await (const chunk of req) {
        content += chunk.toString('utf8');
        if (Buffer.byteLength(content) > 16384) return send(413, { code: 413 });
      }
      const data = Object.fromEntries(new URLSearchParams(content));
      if (Object.keys(data).some(key => !['type', 'key', 'qrimg', 'cookie'].includes(key))) {
        return send(400, { code: 400 });
      }
      const result = await sdk[method]({ ...data, timeout: 10000, randomCNIP: false });
      if (!result || !result.body || typeof result.body !== 'object') return send(502, { code: 502 });
      send(200, result.body); // Authorization cookie is returned to Python in memory, never logged.
    } catch (_) {
      send(502, { code: 502 }); // Never expose upstream exception bodies/headers/cookies.
    }
  });
}

module.exports = { createGateway };
if (require.main === module) {
  // Upstream occasionally logs complete responses on errors. Suppress its console channels.
  for (const name of ['log', 'info', 'debug', 'warn', 'error']) console[name] = () => {};
  for (const name of ['NETEASE_COOKIE', 'NETEASE_CSRF']) delete process.env[name];
  process.env.ENABLE_GENERAL_UNBLOCK = 'false';
  process.env.ENABLE_PROXY = 'false';
  process.env.ENABLE_RANDOM_CN_IP = 'false';
  const port = Number(process.argv[3] || 43871);
  if (!Number.isInteger(port) || (port !== 0 && port < 1024) || port > 65535 || !process.argv[2]) process.exit(1);
  process.on('uncaughtException', () => { process.stderr.write('Login gateway stopped safely.\n'); process.exit(1); });
  process.on('unhandledRejection', () => { process.stderr.write('Login gateway stopped safely.\n'); process.exit(1); });
  const sdkRoot = path.join(path.resolve(process.argv[2]), 'node_modules', '@neteasecloudmusicapienhanced', 'api');
  if (process.env.NETEASE_GATEWAY_DIAGNOSTICS === '1') {
    const fs = require('node:fs');
    const anonymous = path.join(require('node:os').tmpdir(), 'anonymous_token');
    if (!fs.existsSync(anonymous)) fs.writeFileSync(anonymous, '');
    const requestFile = require.resolve(path.join(sdkRoot, 'util', 'request.js'));
    const upstream = require(requestFile);
    require.cache[requestFile].exports = async (...args) => {
      const result = await upstream(...args);
      if (args[0] === '/api/login/qrcode/client/login' && result.body?.code === 803) {
        const known = new Set(['MUSIC_U', '__csrf', 'MUSIC_A', 'MUSIC_R_T', 'NMTID']);
        const names = value => Array.from(new Set(String(value || '').split(';').map(part => part.trim().split('=')[0]).filter(name => known.has(name))));
        process.stdout.write(JSON.stringify({ diagnostic: 'qr-authorized-shape',
          header_count: Array.isArray(result.cookie) ? result.cookie.length : 0,
          header_cookie_names: names((result.cookie || []).join(';')),
          body_cookie_names: names(result.body.cookie),
          body_cookie_nonempty: typeof result.body.cookie === 'string' && result.body.cookie.length > 0 }) + '\n');
      }
      return result;
    };
  }
  const sdk = require(sdkRoot);
  const server = createGateway(sdk);
  server.listen(port, '127.0.0.1', () => process.stdout.write(JSON.stringify({ ready: true, port: server.address().port, login_only: true }) + '\n'));
  // A managed parent's death closes stdin: do not leave an orphaned login service.
  if (!process.stdin.isTTY) {
    process.stdin.resume();
    process.stdin.on('end', () => server.close(() => process.exit(0)));
  }
  setTimeout(() => server.close(() => process.exit(0)), 10 * 60 * 1000).unref();
}
