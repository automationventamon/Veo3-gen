import express      from 'express';
import cors         from 'cors';
import dotenv       from 'dotenv';
import bcrypt       from 'bcryptjs';
import jwt          from 'jsonwebtoken';
import mysql        from 'mysql2/promise';
import multer       from 'multer';
import fetch        from 'node-fetch';
import FormData     from 'form-data';
import fs           from 'fs';
import path         from 'path';
import { randomUUID } from 'crypto';
import { fileURLToPath } from 'url';
import { seedUsers } from './docker/seed-users.js';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app       = express();
const PORT      = process.env.PORT || 3000;

const JWT_SECRET  = process.env.JWT_SECRET  || 'dev-secret-change-me';
const JWT_EXPIRES = process.env.JWT_EXPIRES_IN || '8h';
const VM_URL      = process.env.VM_WORKER_URL || 'http://localhost:8000';

/* ── UPLOAD DIR ───────────────────────────────────────────────── */

const UPLOADS_DIR = path.join(__dirname, 'uploads');
fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const storage = multer.diskStorage({
  destination: (req, _file, cb) => {
    const jobId = req.jobId || (req.jobId = randomUUID());
    const dir   = path.join(UPLOADS_DIR, jobId);
    fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (_req, file, cb) => cb(null, file.originalname),
});
const upload = multer({ storage, limits: { fileSize: 20 * 1024 * 1024 } });

/* ── DATABASE ─────────────────────────────────────────────────── */

let pool;

async function initDatabase() {
  const config = {
    host:     process.env.MYSQL_HOST     || 'localhost',
    port:     parseInt(process.env.MYSQL_PORT || '3306'),
    database: process.env.MYSQL_DATABASE || 'flowgen',
    user:     process.env.MYSQL_USER     || 'flowgen',
    password: process.env.MYSQL_PASSWORD || '',
    waitForConnections: true,
    connectionLimit: 10,
  };

  for (let i = 1; i <= 15; i++) {
    try {
      pool = mysql.createPool(config);
      const conn = await pool.getConnection();
      conn.release();
      console.log(`[db] Connected to MySQL`);
      await seedUsers(pool);
      return;
    } catch (err) {
      console.warn(`[db] Attempt ${i}/15 failed: ${err.message}`);
      if (i === 15) { console.error('[db] Giving up.'); process.exit(1); }
      await new Promise(r => setTimeout(r, 3000));
    }
  }
}

/* ── MIDDLEWARES ──────────────────────────────────────────────── */

app.use(cors({ origin: process.env.CLIENT_URL || '*', credentials: true }));
app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend/dist')));

/* ── AUTH MIDDLEWARE ──────────────────────────────────────────── */

async function requireAuth(req, res, next) {
  // Support token via Authorization header OR query param (for download links)
  const raw = req.headers['authorization'] || (req.query.token ? `Bearer ${req.query.token}` : null);
  if (!raw?.startsWith('Bearer ')) return res.status(401).json({ error: 'Authentication required.' });

  const token = raw.slice(7);
  let decoded;
  try {
    decoded = jwt.verify(token, JWT_SECRET);
  } catch (err) {
    const msg = err.name === 'TokenExpiredError' ? 'Session expired.' : 'Invalid token.';
    return res.status(401).json({ error: msg });
  }

  if (pool && decoded.jti) {
    try {
      const [rows] = await pool.query('SELECT revoked FROM sessions WHERE jti = ?', [decoded.jti]);
      if (rows[0]?.revoked === 1) return res.status(401).json({ error: 'Session revoked.' });
    } catch {}
  }

  req.user = decoded;
  next();
}

/* ── ROUTES ───────────────────────────────────────────────────── */

app.get('/api/health', (_req, res) => res.json({ status: 'ok', db: pool ? 'connected' : 'disconnected', vm: VM_URL }));

/* LOGIN */
app.post('/api/login', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: 'Username and password are required.' });

  const safe = String(username).trim().toLowerCase();
  if (!pool) return res.status(503).json({ error: 'Database not available.' });

  try {
    const [rows] = await pool.query('SELECT id, username, password, active FROM users WHERE username = ?', [safe]);
    const hash   = rows[0]?.password || '$2a$12$invalidhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX';
    const match  = await bcrypt.compare(password, hash);

    if (!rows[0] || !match)   return res.status(401).json({ error: 'Invalid username or password.' });
    if (!rows[0].active)       return res.status(403).json({ error: 'Account is disabled.' });

    const jti       = randomUUID();
    const expiresAt = new Date(Date.now() + parseExpiry(JWT_EXPIRES));

    await pool.query('INSERT INTO sessions (user_id, jti, expires_at) VALUES (?, ?, ?)', [rows[0].id, jti, expiresAt]).catch(() => {});
    pool.query('UPDATE users SET last_login = NOW() WHERE id = ?', [rows[0].id]).catch(() => {});

    const token = jwt.sign({ sub: rows[0].id, username: rows[0].username, jti }, JWT_SECRET, { expiresIn: JWT_EXPIRES });
    return res.json({ token, username: rows[0].username });
  } catch (err) {
    return res.status(500).json({ error: 'Internal server error.' });
  }
});

/* LOGOUT */
app.post('/api/logout', requireAuth, async (req, res) => {
  if (pool && req.user.jti) {
    await pool.query('UPDATE sessions SET revoked = 1 WHERE jti = ?', [req.user.jti]).catch(() => {});
  }
  return res.json({ message: 'Logged out.' });
});

/* CREATE JOB */
app.post('/api/jobs', requireAuth, (req, res, next) => {
  upload.array('images')(req, res, (err) => {
    if (err) return res.status(400).json({ error: err.message });
    next();
  });
}, async (req, res) => {
  const files = req.files;
  if (!files?.length) return res.status(400).json({ error: 'No images received.' });

  const prompts  = JSON.parse(req.body.prompts || '{}');
  const jobId    = req.jobId; // set by multer destination

  try {
    // Save job in DB
    await pool.query(
      'INSERT INTO jobs (id, user_id, status, total_images) VALUES (?, ?, ?, ?)',
      [jobId, req.user.sub, 'pending', files.length]
    );

    // Send to VM worker (async — don't await)
    sendToVM(jobId, files, prompts).catch((err) => {
      console.error(`[job ${jobId}] VM error:`, err.message);
      pool.query("UPDATE jobs SET status='error', error_msg=? WHERE id=?", [err.message, jobId]).catch(() => {});
    });

    const [rows] = await pool.query('SELECT * FROM jobs WHERE id = ?', [jobId]);
    return res.status(201).json(formatJob(rows[0]));
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

/* LIST JOBS */
app.get('/api/jobs', requireAuth, async (req, res) => {
  const [rows] = await pool.query(
    'SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50',
    [req.user.sub]
  );
  return res.json(rows.map(formatJob));
});

/* GET JOB */
app.get('/api/jobs/:id', requireAuth, async (req, res) => {
  const [rows] = await pool.query('SELECT * FROM jobs WHERE id = ? AND user_id = ?', [req.params.id, req.user.sub]);
  if (!rows[0]) return res.status(404).json({ error: 'Job not found.' });

  // If running/pending, refresh status from VM
  const job = rows[0];
  if ((job.status === 'running' || job.status === 'pending') && job.vm_job_id) {
    try {
      const vmRes  = await fetch(`${VM_URL}/api/job/${job.vm_job_id}`);
      const vmData = await vmRes.json();
      await pool.query(
        'UPDATE jobs SET status=?, done_images=?, error_msg=? WHERE id=?',
        [vmData.status, vmData.progress?.done || 0, vmData.error || null, job.id]
      );
      Object.assign(job, { status: vmData.status, done_images: vmData.progress?.done || 0 });
    } catch {}
  }

  return res.json(formatJob(job));
});

/* DOWNLOAD JOB */
app.get('/api/jobs/:id/download', requireAuth, async (req, res) => {
  const [rows] = await pool.query('SELECT * FROM jobs WHERE id = ? AND user_id = ?', [req.params.id, req.user.sub]);
  if (!rows[0]) return res.status(404).json({ error: 'Job not found.' });
  if (rows[0].status !== 'done') return res.status(400).json({ error: 'Job not finished yet.' });

  try {
    const vmRes = await fetch(`${VM_URL}/api/job/${rows[0].vm_job_id}/download`);
    if (!vmRes.ok) return res.status(502).json({ error: 'Could not fetch videos from worker.' });
    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="videos-${req.params.id.slice(0,8)}.zip"`);
    vmRes.body.pipe(res);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

/* ── SPA FALLBACK ─────────────────────────────────────────────── */

app.get('*', (req, res) => {
  if (!req.path.startsWith('/api')) {
    res.sendFile(path.join(__dirname, '../frontend/dist/index.html'));
  } else {
    res.status(404).json({ error: 'Not found.' });
  }
});

/* ── HELPERS ──────────────────────────────────────────────────── */

function formatJob(row) {
  return {
    id:          row.id,
    status:      row.status,
    totalImages: row.total_images,
    doneImages:  row.done_images,
    errorMsg:    row.error_msg || null,
    createdAt:   row.created_at,
    updatedAt:   row.updated_at,
  };
}

async function sendToVM(jobId, files, prompts) {
  const form = new FormData();
  form.append('job_id', jobId);
  form.append('prompts', JSON.stringify(prompts));

  for (const file of files) {
    form.append('images', fs.createReadStream(file.path), file.originalname);
  }

  const res  = await fetch(`${VM_URL}/api/job`, { method: 'POST', body: form });
  const data = await res.json();

  if (!res.ok) throw new Error(data.error || `VM responded with ${res.status}`);

  // Update job with VM's job id and set to running
  await pool.query("UPDATE jobs SET vm_job_id=?, status='running' WHERE id=?", [data.job_id, jobId]);
}

function parseExpiry(exp) {
  const m = String(exp).match(/^(\d+)([smhd])$/);
  if (!m) return 8 * 3_600_000;
  const mult = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
  return parseInt(m[1]) * (mult[m[2]] || 3_600_000);
}

/* ── START ────────────────────────────────────────────────────── */

async function main() {
  await initDatabase();
  app.listen(PORT, () => {
    console.log(`✦ FlowGen backend running at http://localhost:${PORT}`);
    console.log(`✦ VM Worker URL: ${VM_URL}`);
  });
}

main().catch((err) => { console.error('[startup]', err); process.exit(1); });
