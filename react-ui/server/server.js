/**
 * server.js — Express API backend for AI Employee Vault React UI
 *
 * Endpoints:
 *   POST /api/auth/login        — JWT auth (env-based password)
 *   GET  /api/dashboard         — Parse + return Dashboard.md + Business_Goals.md as HTML
 *   GET  /api/pending           — List /Pending_Approval files
 *   POST /api/pending/:file/approve  — Move file to /Approved
 *   POST /api/pending/:file/reject   — Move file to /Rejected
 *   POST /api/task              — Drop a new file into /Needs_Action
 *   GET  /api/logs              — Read /Logs/*.jsonl (last N entries)
 *   POST /api/audit             — Trigger orchestrator --simulate --once
 *   GET  /health                — Health check
 *
 * JWT: Bearer token in Authorization header (1h expiry)
 * Serve React build from ../client/build in production.
 */

require('dotenv').config();

const express    = require('express');
const jwt        = require('jsonwebtoken');
const cors       = require('cors');
const morgan     = require('morgan');
const helmet     = require('helmet');
const rateLimit  = require('express-rate-limit');
const fs         = require('fs');
const path       = require('path');
const { execFile, spawn } = require('child_process');
const { marked } = require('marked');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const PORT       = parseInt(process.env.PORT   || '3001', 10);
const HOST       = process.env.HOST             || '127.0.0.1';
const JWT_SECRET = process.env.JWT_SECRET       || 'dev-jwt-secret-change-in-prod';
const UI_PASS    = process.env.UI_PASSWORD       || 'admin';
const VAULT_DIR  = process.env.VAULT_DIR         || 'd:/hackathon0/hackathon/AI_Employee_Vault';

const PENDING_DIR    = path.join(VAULT_DIR, 'Pending_Approval');
const APPROVED_DIR   = path.join(VAULT_DIR, 'Approved');
const REJECTED_DIR   = path.join(VAULT_DIR, 'Rejected');
const NEEDS_ACT_DIR  = path.join(VAULT_DIR, 'Needs_Action');
const DASHBOARD_FILE = path.join(VAULT_DIR, 'Dashboard.md');
const GOALS_FILE     = path.join(VAULT_DIR, 'Business_Goals.md');
const LOGS_DIR       = path.join(VAULT_DIR, 'Logs');
const ORCH_FILE      = path.join(VAULT_DIR, 'orchestrator.py');
const CLIENT_BUILD   = path.join(__dirname, '..', 'client', 'build');

// Ensure dirs exist
for (const d of [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, NEEDS_ACT_DIR, LOGS_DIR]) {
  fs.mkdirSync(d, { recursive: true });
}

// ---------------------------------------------------------------------------
// App setup
// ---------------------------------------------------------------------------
const app = express();

app.use(helmet({ contentSecurityPolicy: false }));  // CSP off for dev
app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '1mb' }));
app.use(morgan('dev'));

// Rate limiting
const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 20, message: { error: 'Too many login attempts' } });
const apiLimiter  = rateLimit({ windowMs: 60 * 1000, max: 120 });
app.use('/api/auth', authLimiter);
app.use('/api', apiLimiter);

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------
const LOG_FILE = path.join(VAULT_DIR, 'react-ui.log');
function log(level, msg, data = {}) {
  const entry = JSON.stringify({ ts: new Date().toISOString(), level, msg, ...data });
  try { fs.appendFileSync(LOG_FILE, entry + '\n', 'utf8'); } catch {}
  console.log(`[${level}] ${msg}`, Object.keys(data).length ? data : '');
}

// ---------------------------------------------------------------------------
// In-memory audit events (last 100)
// ---------------------------------------------------------------------------
const uiEvents = [];
function recordEvent(action, detail = '', success = true, user = 'unknown') {
  const ev = { ts: new Date().toISOString(), action, detail, success, user };
  uiEvents.push(ev);
  if (uiEvents.length > 100) uiEvents.shift();
  log(success ? 'INFO' : 'WARN', `${action}: ${detail}`, { user, success });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function sanitizeFilename(name) {
  // Allow alphanumeric, dots, dashes, underscores, spaces (path.basename handles traversal)
  return path.basename(name).replace(/[^a-zA-Z0-9._\- ]/g, '_');
}

function safeMovePending(filename, destDir) {
  const safe = sanitizeFilename(filename);
  const src  = path.join(PENDING_DIR, safe);
  const dst  = path.join(destDir, safe);
  if (!fs.existsSync(src)) throw new Error(`File not found: ${safe}`);
  fs.renameSync(src, dst);
  return { moved: safe, to: path.basename(destDir) };
}

function parseYamlFrontmatter(text) {
  if (!text.startsWith('---')) return {};
  const end = text.indexOf('---', 3);
  if (end === -1) return {};
  const meta = {};
  text.slice(3, end).split('\n').forEach(line => {
    const m = line.trim().match(/^([\w_-]+):\s*(.*)$/);
    if (m) meta[m[1]] = m[2].trim();
  });
  return meta;
}

function readMarkdownAsHtml(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return { html: marked.parse(raw), raw };
  } catch (e) {
    if (e.code === 'ENOENT') return { html: '<p><em>File not found.</em></p>', raw: '' };
    throw e;
  }
}

function readLastLogs(n = 200) {
  const entries = [];
  try {
    const files = fs.readdirSync(LOGS_DIR)
      .filter(f => f.endsWith('.jsonl') || f.endsWith('.log'))
      .sort().reverse().slice(0, 5);
    for (const f of files) {
      const lines = fs.readFileSync(path.join(LOGS_DIR, f), 'utf8')
        .split('\n').filter(Boolean);
      for (const l of lines.reverse()) {
        try { entries.push(JSON.parse(l)); } catch { entries.push({ raw: l }); }
        if (entries.length >= n) break;
      }
      if (entries.length >= n) break;
    }
  } catch (e) {
    log('WARN', 'Error reading logs: ' + e.message);
  }
  return entries.slice(0, n);
}

// ---------------------------------------------------------------------------
// JWT middleware
// ---------------------------------------------------------------------------
function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token  = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'No token provided' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch (e) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

// Health
app.get('/health', (req, res) => {
  res.json({ status: 'ok', vault: VAULT_DIR, ts: new Date().toISOString() });
});

// --- Auth ---
app.post('/api/auth/login', (req, res) => {
  const { password } = req.body;
  if (!password || password !== UI_PASS) {
    recordEvent('login_fail', 'Bad password', false);
    return res.status(401).json({ error: 'Incorrect password' });
  }
  const token = jwt.sign({ user: 'admin' }, JWT_SECRET, { expiresIn: '1h' });
  recordEvent('login', 'Successful login', true, 'admin');
  res.json({ token, expiresIn: 3600 });
});

// --- Dashboard ---
app.get('/api/dashboard', requireAuth, (req, res) => {
  try {
    const dashboard = readMarkdownAsHtml(DASHBOARD_FILE);
    const goals     = readMarkdownAsHtml(GOALS_FILE);
    res.json({
      dashboard: { html: dashboard.html },
      goals:     { html: goals.html },
      ts: new Date().toISOString(),
    });
  } catch (e) {
    log('ERROR', 'Dashboard error: ' + e.message);
    res.status(500).json({ error: e.message });
  }
});

// --- Pending Approval ---
app.get('/api/pending', requireAuth, (req, res) => {
  try {
    const files = fs.readdirSync(PENDING_DIR)
      .filter(f => f.endsWith('.md'))
      .sort()
      .map(f => {
        const fullPath = path.join(PENDING_DIR, f);
        let raw = '';
        try { raw = fs.readFileSync(fullPath, 'utf8'); } catch {}
        const meta = parseYamlFrontmatter(raw);
        const body = raw.startsWith('---')
          ? raw.slice(raw.indexOf('---', 3) + 3).trim()
          : raw;
        const stat = fs.statSync(fullPath);
        return {
          filename: f,
          stem:     path.basename(f, '.md'),
          meta,
          body:     body.slice(0, 400) + (body.length > 400 ? '…' : ''),
          category: meta.type || meta.category || 'item',
          modified: stat.mtime.toISOString(),
          size:     stat.size,
        };
      });
    res.json(files);
  } catch (e) {
    log('ERROR', 'Pending list error: ' + e.message);
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/pending/:file/approve', requireAuth, (req, res) => {
  try {
    const result = safeMovePending(req.params.file, APPROVED_DIR);
    recordEvent('approve', result.moved, true, req.user?.user);
    res.json({ ok: true, ...result });
  } catch (e) {
    recordEvent('approve_fail', e.message, false, req.user?.user);
    res.status(e.message.includes('not found') ? 404 : 500).json({ ok: false, error: e.message });
  }
});

app.post('/api/pending/:file/reject', requireAuth, (req, res) => {
  try {
    const result = safeMovePending(req.params.file, REJECTED_DIR);
    recordEvent('reject', result.moved, true, req.user?.user);
    res.json({ ok: true, ...result });
  } catch (e) {
    recordEvent('reject_fail', e.message, false, req.user?.user);
    res.status(e.message.includes('not found') ? 404 : 500).json({ ok: false, error: e.message });
  }
});

// --- Task Creator ---
app.post('/api/task', requireAuth, (req, res) => {
  try {
    const { title = 'Task', content = '', category = 'manual' } = req.body;
    if (!content.trim()) return res.status(400).json({ error: 'Content is required' });
    const safe = title.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 40);
    const ts   = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const filename = `${safe}_${ts}.md`;
    const body = `---\ntitle: ${title}\ncategory: ${category}\ncreated: ${new Date().toISOString()}\nstatus: pending\n---\n\n${content}\n`;
    fs.writeFileSync(path.join(NEEDS_ACT_DIR, filename), body, 'utf8');
    recordEvent('task_create', filename, true, req.user?.user);
    res.json({ ok: true, filename });
  } catch (e) {
    log('ERROR', 'Task create error: ' + e.message);
    res.status(500).json({ ok: false, error: e.message });
  }
});

// --- Logs viewer ---
app.get('/api/logs', requireAuth, (req, res) => {
  try {
    const n = Math.min(parseInt(req.query.n || '100', 10), 500);
    const entries = readLastLogs(n);
    res.json({ entries, count: entries.length });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// --- Manual audit trigger ---
app.post('/api/audit', requireAuth, (req, res) => {
  recordEvent('audit_trigger', 'Manual orchestrator run', true, req.user?.user);
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const proc   = spawn(python, [ORCH_FILE, '--simulate', '--once'], {
    cwd: VAULT_DIR, encoding: 'utf8',
  });
  let output = '';
  proc.stdout.on('data', d => { output += d; });
  proc.stderr.on('data', d => { output += d; });

  const timer = setTimeout(() => {
    proc.kill();
    output += '\n(timed out after 30s)';
  }, 30000);

  proc.on('close', code => {
    clearTimeout(timer);
    const ok = code === 0;
    recordEvent('audit_result', output.slice(-200), ok, req.user?.user);
    res.json({ ok, code, output: output.split('\n').filter(Boolean).slice(-15).join('\n') });
  });
});

// --- Events API ---
app.get('/api/events', requireAuth, (req, res) => {
  res.json([...uiEvents].reverse().slice(0, 50));
});

// Serve React build in production
if (fs.existsSync(CLIENT_BUILD)) {
  app.use(express.static(CLIENT_BUILD));
  app.get('*', (req, res) => res.sendFile(path.join(CLIENT_BUILD, 'index.html')));
}

// ---------------------------------------------------------------------------
// Error handler
// ---------------------------------------------------------------------------
app.use((err, req, res, next) => {
  log('ERROR', err.message, { stack: err.stack?.slice(0, 300) });
  res.status(500).json({ error: 'Internal server error' });
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
if (require.main === module) {
  app.listen(PORT, HOST, () => {
    log('INFO', `AI Employee Vault API running on http://${HOST}:${PORT}`);
    log('INFO', `Vault: ${VAULT_DIR}`);
  });
}

module.exports = { app, recordEvent, safeMovePending, parseYamlFrontmatter, readMarkdownAsHtml, readLastLogs, sanitizeFilename };
