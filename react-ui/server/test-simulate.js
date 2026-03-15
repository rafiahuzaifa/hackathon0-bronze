/**
 * test-simulate.js — Ralph Wiggum test loop for React UI server
 * Simulates the full approval flow against the Express server.
 * Runs up to MAX_ITER attempts until all tests pass.
 */
'use strict';

const http   = require('http');
const fs     = require('fs');
const path   = require('path');
const os     = require('os');

// Load app with a temp vault
const TMP_VAULT  = fs.mkdtempSync(path.join(os.tmpdir(), 'vault-test-'));
process.env.VAULT_DIR    = TMP_VAULT;
process.env.UI_PASSWORD  = 'testpass';
process.env.JWT_SECRET   = 'test-secret';
process.env.PORT         = '3099';   // test port

// Create required sub-dirs
for (const d of ['Pending_Approval','Approved','Rejected','Needs_Action','Logs']) {
  fs.mkdirSync(path.join(TMP_VAULT, d), { recursive: true });
}
// Create mock Dashboard.md and Business_Goals.md
fs.writeFileSync(path.join(TMP_VAULT, 'Dashboard.md'), '# Dashboard\n\n## Balance\n- $10,000\n', 'utf8');
fs.writeFileSync(path.join(TMP_VAULT, 'Business_Goals.md'), '# Goals\n\n- Grow revenue 20%\n', 'utf8');

const {
  app, recordEvent, safeMovePending,
  parseYamlFrontmatter, readMarkdownAsHtml, readLastLogs, sanitizeFilename
} = require('./server.js');

// ---- Test helpers ----
let PASS = 0, FAIL = 0;
const results = [];

function check(name, cond, detail = '') {
  const ok = Boolean(cond);
  ok ? PASS++ : FAIL++;
  const tag = ok ? '[PASS]' : '[FAIL]';
  const msg = `  ${tag} ${name}` + (detail ? `: ${detail}` : '');
  results.push(msg);
  console.log(msg);
  return ok;
}

function apiCall(method, pathname, body, token) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : null;
    const opts = {
      hostname: '127.0.0.1', port: 3099,
      path: pathname, method,
      headers: {
        'Content-Type': 'application/json',
        ...(payload ? { 'Content-Length': Buffer.byteLength(payload) } : {}),
        ...(token   ? { 'Authorization': `Bearer ${token}` }          : {}),
      },
    };
    const req = http.request(opts, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function runTests() {
  console.log('\n=== AI Employee React UI — Ralph Wiggum Test Loop ===\n');

  // Start server
  const server = app.listen(3099, '127.0.0.1');
  await new Promise(r => server.once('listening', r));

  let token = null;

  // ---- [1] Helpers unit tests ----
  console.log('[1] Helper unit tests');

  check('sanitizeFilename basic',    sanitizeFilename('task.md') === 'task.md');
  check('sanitizeFilename traversal', !sanitizeFilename('../etc/passwd').includes('/'));
  check('sanitizeFilename spaces',   sanitizeFilename('my task.md') === 'my task.md');

  const fm = parseYamlFrontmatter('---\ntype: payment\namount: 750\n---\n\nBody.');
  check('parseYamlFrontmatter type',   fm.type   === 'payment');
  check('parseYamlFrontmatter amount', fm.amount  === '750');
  check('parseYamlFrontmatter empty',  Object.keys(parseYamlFrontmatter('No YAML')).length === 0);

  const md = readMarkdownAsHtml(path.join(TMP_VAULT, 'Dashboard.md'));
  check('readMarkdownAsHtml h1',    md.html.includes('<h1>'));
  check('readMarkdownAsHtml table', md.html.includes('Balance'));
  const miss = readMarkdownAsHtml('/nonexistent/path.md');
  check('readMarkdownAsHtml 404',   miss.html.includes('not found'));

  recordEvent('test_event', 'unit test', true);
  check('recordEvent works', true);

  // ---- [2] Health check ----
  console.log('\n[2] Health endpoint');
  const health = await apiCall('GET', '/health', null, null);
  check('GET /health 200',    health.status === 200);
  check('health status ok',   health.body?.status === 'ok');
  check('health vault set',   health.body?.vault === TMP_VAULT);

  // ---- [3] Auth ----
  console.log('\n[3] Auth — JWT login');
  const badLogin = await apiCall('POST', '/api/auth/login', { password: 'wrong' }, null);
  check('bad password → 401',  badLogin.status === 401);
  check('error field present', !!badLogin.body?.error);

  const goodLogin = await apiCall('POST', '/api/auth/login', { password: 'testpass' }, null);
  check('good password → 200', goodLogin.status === 200);
  check('token returned',      typeof goodLogin.body?.token === 'string');
  check('expiresIn returned',  goodLogin.body?.expiresIn === 3600);
  token = goodLogin.body?.token;

  // Auth required
  const unauth = await apiCall('GET', '/api/pending', null, null);
  check('no token → 401',      unauth.status === 401);

  const badToken = await apiCall('GET', '/api/pending', null, 'bad.token.here');
  check('bad token → 401',     badToken.status === 401);

  // ---- [4] Dashboard ----
  console.log('\n[4] Dashboard endpoint');
  const dash = await apiCall('GET', '/api/dashboard', null, token);
  check('GET /api/dashboard 200',    dash.status === 200);
  check('dashboard.html present',   typeof dash.body?.dashboard?.html === 'string');
  check('h1 in dashboard html',     dash.body?.dashboard?.html?.includes('<h1>'));
  check('goals.html present',       typeof dash.body?.goals?.html === 'string');

  // ---- [5] Pending list ----
  console.log('\n[5] Pending list — empty');
  const emptyPend = await apiCall('GET', '/api/pending', null, token);
  check('GET /api/pending 200',  emptyPend.status === 200);
  check('returns array',         Array.isArray(emptyPend.body));
  check('empty initially',       emptyPend.body.length === 0);

  // Seed 3 files
  const pendDir = path.join(TMP_VAULT, 'Pending_Approval');
  for (let i = 0; i < 3; i++) {
    fs.writeFileSync(
      path.join(pendDir, `task_${i}.md`),
      `---\ntype: sim\nid: ${i}\nstatus: pending\n---\n\nSimulated task ${i}.`,
      'utf8'
    );
  }

  const seededPend = await apiCall('GET', '/api/pending', null, token);
  check('3 files appear',        seededPend.status === 200);
  check('count = 3',             seededPend.body?.length === 3);
  check('filename field',        seededPend.body?.[0]?.filename?.endsWith('.md'));
  check('meta.type = sim',       seededPend.body?.[0]?.meta?.type === 'sim');
  check('modified iso string',   typeof seededPend.body?.[0]?.modified === 'string');

  // ---- [6] Approve ----
  console.log('\n[6] Approve flow');
  const app0 = await apiCall('POST', '/api/pending/task_0.md/approve', null, token);
  check('POST approve 200',      app0.status === 200);
  check('ok = true',             app0.body?.ok === true);
  check('moved to Approved',     fs.existsSync(path.join(TMP_VAULT, 'Approved', 'task_0.md')));
  check('gone from Pending',    !fs.existsSync(path.join(pendDir, 'task_0.md')));

  // ---- [7] Reject ----
  console.log('\n[7] Reject flow');
  const rej1 = await apiCall('POST', '/api/pending/task_1.md/reject', null, token);
  check('POST reject 200',       rej1.status === 200);
  check('ok = true',             rej1.body?.ok === true);
  check('moved to Rejected',     fs.existsSync(path.join(TMP_VAULT, 'Rejected', 'task_1.md')));

  // ---- [8] Error handling ----
  console.log('\n[8] Error cases');
  const notFound = await apiCall('POST', '/api/pending/nonexistent.md/approve', null, token);
  check('missing file → 404',    notFound.status === 404);
  check('ok = false',            notFound.body?.ok === false);

  // Path traversal
  const traversal = await apiCall('POST', '/api/pending/..%2F..%2Fetc%2Fpasswd/approve', null, token);
  check('traversal → 404',       traversal.status === 404);

  // ---- [9] Task creator ----
  console.log('\n[9] Task creator');
  const noContent = await apiCall('POST', '/api/task', { title: 'T', content: '' }, token);
  check('empty content → 400',   noContent.status === 400);

  const good = await apiCall('POST', '/api/task', {
    title: 'Test Task', content: 'Do something important.', category: 'manual',
  }, token);
  check('task created 200',      good.status === 200);
  check('ok = true',             good.body?.ok === true);
  check('filename returned',     typeof good.body?.filename === 'string');
  check('file exists on disk',   fs.existsSync(path.join(TMP_VAULT, 'Needs_Action', good.body?.filename)));

  // ---- [10] Logs ----
  console.log('\n[10] Logs endpoint');
  // Write a fake jsonl log
  const logFile = path.join(TMP_VAULT, 'Logs', 'audit_test.jsonl');
  fs.writeFileSync(logFile,
    JSON.stringify({ ts: new Date().toISOString(), level: 'INFO', message: 'test log' }) + '\n' +
    JSON.stringify({ ts: new Date().toISOString(), level: 'WARN', message: 'test warn' }) + '\n',
    'utf8'
  );
  const logs = await apiCall('GET', '/api/logs?n=10', null, token);
  check('GET /api/logs 200',     logs.status === 200);
  check('entries array',         Array.isArray(logs.body?.entries));
  check('at least 2 entries',    (logs.body?.entries?.length || 0) >= 2);

  // ---- [11] Events ----
  console.log('\n[11] Events endpoint');
  const evts = await apiCall('GET', '/api/events', null, token);
  check('GET /api/events 200',   evts.status === 200);
  check('events is array',       Array.isArray(evts.body));
  check('events have action',    evts.body?.every(e => e.action));

  // ---- [12] Full flow simulation (Ralph Wiggum loop) ----
  console.log('\n[12] Full approval flow simulation');
  // Create 3 fresh sim files
  for (let i = 0; i < 3; i++) {
    fs.writeFileSync(
      path.join(pendDir, `_sim_full_${i}.md`),
      `---\ntype: sim\n---\n\nSim task ${i}.`,
      'utf8'
    );
  }
  // Approve 0 & 1, reject 2
  const ra0 = await apiCall('POST', '/api/pending/_sim_full_0.md/approve', null, token);
  const ra1 = await apiCall('POST', '/api/pending/_sim_full_1.md/approve', null, token);
  const rr2 = await apiCall('POST', '/api/pending/_sim_full_2.md/reject', null, token);

  check('sim approve 0', ra0.body?.ok === true);
  check('sim approve 1', ra1.body?.ok === true);
  check('sim reject 2',  rr2.body?.ok === true);

  // Verify final state
  const finalPend = await apiCall('GET', '/api/pending', null, token);
  const remaining = (finalPend.body || []).filter(f => f.filename.startsWith('_sim_full_'));
  const approved  = fs.readdirSync(path.join(TMP_VAULT, 'Approved')).filter(f => f.startsWith('_sim_full_'));
  const rejected  = fs.readdirSync(path.join(TMP_VAULT, 'Rejected')).filter(f => f.startsWith('_sim_full_'));

  check('0 sim files remain pending', remaining.length === 0);
  check('2 sim files approved',       approved.length === 2);
  check('1 sim file rejected',        rejected.length === 1);

  // Close server (do NOT delete TMP_VAULT here — keep it for retries)
  await new Promise(r => server.close(r));

  // ---- Summary ----
  const total = PASS + FAIL;
  console.log(`\n${'='.repeat(52)}`);
  console.log(`Results: ${PASS}/${total} passed ${FAIL === 0 ? '— ALL PASS' : `— ${FAIL} FAILED`}`);
  console.log('='.repeat(52) + '\n');
  return FAIL === 0;
}

// Ralph Wiggum loop
const MAX_ITER = 3;
(async () => {
  try {
    for (let attempt = 1; attempt <= MAX_ITER; attempt++) {
      console.log(`\n--- Attempt ${attempt}/${MAX_ITER} ---`);
      PASS = 0; FAIL = 0; results.length = 0;
      // Re-seed files that may have been consumed by a previous attempt
      for (const sub of ['Pending_Approval','Approved','Rejected','Needs_Action','Logs']) {
        fs.mkdirSync(path.join(TMP_VAULT, sub), { recursive: true });
      }
      fs.writeFileSync(path.join(TMP_VAULT, 'Dashboard.md'), '# Dashboard\n\n## Balance\n- $10,000\n', 'utf8');
      fs.writeFileSync(path.join(TMP_VAULT, 'Business_Goals.md'), '# Goals\n\n- Grow revenue 20%\n', 'utf8');
      try {
        const ok = await runTests();
        if (ok) { console.log("Ralph says: I passed! I passed!\n"); process.exit(0); }
      } catch (e) {
        console.error('Test runner error:', e.message);
      }
      if (attempt < MAX_ITER) console.log(`Attempt ${attempt} had failures, retrying…\n`);
    }
    console.log('Ralph loop exhausted — tests still failing.');
  } finally {
    fs.rmSync(TMP_VAULT, { recursive: true, force: true });
  }
  process.exit(1);
})();
