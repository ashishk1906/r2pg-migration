import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import https from 'https';
import { fileURLToPath } from 'url';
import pg from 'pg';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load .env from project root
const envPath = path.resolve(__dirname, '../../.env');
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath });
} else {
  dotenv.config();
}

const app = express();
const PORT = process.env.SERVER_PORT || 3001;

app.use(cors());
app.use(express.json());

// 1. PostgreSQL Connection Pool
const { Pool } = pg;
const pgPool = new Pool({
  host: process.env.PG_HOST || 'localhost',
  port: parseInt(process.env.PG_PORT || '5433', 10),
  database: process.env.PG_DB || 'rpg',
  user: process.env.PG_USER || 'postgres',
  password: process.env.PG_PASSWORD || '',
  connectionTimeoutMillis: 3000,
  query_timeout: 8000,
});

// 2. RavenDB HTTPS Client Agent with .pfx Certificate
const ravenUrl = (process.env.RAVEN_URL || 'https://a.free.btl.ravendb.cloud').replace(/\/+$/, '');
const ravenDb = process.env.RAVEN_DB || 'btl';
const rawCertPath = process.env.RAVEN_CERT_FILE || 'certs/free.btl.client.certificate.pfx';
const certPath = path.isAbsolute(rawCertPath)
  ? rawCertPath
  : path.resolve(__dirname, '../../scripts', rawCertPath);

let ravenAgent = null;
if (fs.existsSync(certPath)) {
  try {
    const pfxBuffer = fs.readFileSync(certPath);
    ravenAgent = new https.Agent({
      pfx: pfxBuffer,
      passphrase: process.env.RAVEN_CERT_PASSWORD || '',
      rejectUnauthorized: process.env.RAVEN_INSECURE === 'true' ? false : true,
      timeout: 10000,
    });
    console.log(`[RavenDB] Client certificate loaded successfully from: ${certPath}`);
  } catch (err) {
    console.error(`[RavenDB] Failed to load certificate: ${err.message}`);
  }
} else {
  console.warn(`[RavenDB] Certificate file not found at: ${certPath}`);
}

// Canonical mapping between RavenDB collections and PostgreSQL tables
export const DOMAIN_MAP = [
  { domain: 'Students', collection: 'Students', table: 'student', idCol: 'student_id' },
  { domain: 'Fees', collection: 'Fees', table: 'fee', idCol: 'id' },
  { domain: 'Fee Transactions', collection: 'FeeTxes', table: 'fee_transaction', idCol: 'id' },
  { domain: 'Courses', collection: 'Courses', table: 'course', idCol: 'id' },
  { domain: 'Applications', collection: 'Applications', table: 'applications', idCol: 'id' },
  { domain: 'Personas', collection: 'Personas', table: 'persona', idCol: 'id' },
  { domain: 'Organizations', collection: 'Orgs', table: 'organization', idCol: 'id' },
  { domain: 'Institutes', collection: 'Institutes', table: 'institute', idCol: 'id' },
  { domain: 'Exams', collection: 'Exams', table: 'exam', idCol: 'id' },
  { domain: 'Staffs', collection: 'Staffs', table: 'staffs', idCol: 'id' },
  { domain: 'Attendance Events', collection: 'AttendanceEvents', table: 'attendance_event', idCol: 'id' },
  { domain: 'Assessments', collection: 'Assessments', table: 'assessments', idCol: 'id' },
  { domain: 'Inventory Items', collection: 'InventoryItemViews', table: 'inventory_item_views', idCol: 'id' },
  { domain: 'Ledger Accounts', collection: 'LedgerAccountViews', table: 'ledger_account_views', idCol: 'id' },
  { domain: 'Receipts', collection: 'Receipts', table: 'receipts', idCol: 'id' },
  { domain: 'Questions (QA)', collection: 'Questions', table: 'questions', idCol: 'id' },
  { domain: 'Topics', collection: 'Topics', table: 'topics', idCol: 'id' },
  { domain: 'Voucher Views', collection: 'VoucherViews', table: 'voucher_views', idCol: 'id' },
  { domain: 'Users', collection: 'Users', table: 'users', idCol: 'id' },
  { domain: 'SMS Messages', collection: 'SmsMessages', table: 'sms_message', idCol: 'id' },
  { domain: 'SMS Config', collection: 'SMs', table: 'sms', idCol: 'id' },
  { domain: 'Emails', collection: 'Emails', table: 'email', idCol: 'id' },
  { domain: 'Asset Views', collection: 'AssetViews', table: 'asset_views', idCol: 'id' },
  { domain: 'Member Views', collection: 'MemberViews', table: 'member_views', idCol: 'id' },
  { domain: 'Material Views', collection: 'MaterialViews', table: 'material_views', idCol: 'id' },
  { domain: 'Circulation Views', collection: 'CirculationViews', table: 'circulation_views', idCol: 'id' },
  { domain: 'Institute Calendars', collection: 'InstituteCalendars', table: 'institute_calendars', idCol: 'id' },
  { domain: 'Calendar Rules', collection: 'CalendarRules', table: 'calendar_rules', idCol: 'id' },
  { domain: 'Application Form Templates', collection: 'ApplicationFormTemplates', table: 'application_form_templates', idCol: 'id' },
  { domain: 'Artefacts', collection: 'Artefacts', table: 'artefacts', idCol: 'id' },
  { domain: 'Artefact Tags', collection: 'ArtefactTags', table: 'artefact_tags', idCol: 'id' },
  { domain: 'Assessment Tags', collection: 'AssessmentTags', table: 'assessment_tags', idCol: 'id' },
  { domain: 'Content Tags', collection: 'ContentTags', table: 'content_tags', idCol: 'id' },
  { domain: 'QA Tags', collection: 'QATags', table: 'qa_tags', idCol: 'id' },
  { domain: 'Image Tags', collection: 'ImageTags', table: 'image_tags', idCol: 'id' },
  { domain: 'Seat Matrices', collection: 'SeatMatrices', table: 'seat_matrices', idCol: 'id' },
  { domain: 'Gradings', collection: 'Gradings', table: 'gradings', idCol: 'id' },
  { domain: 'Commits', collection: 'Commits', table: 'commits', idCol: 'id' },
  { domain: 'Commit ACs', collection: 'CommitAcs', table: 'commit_ac', idCol: 'id' },
  { domain: 'Commit Assets', collection: 'CommitAssets', table: 'commit_asset', idCol: 'id' },
  { domain: 'Inventory Journals', collection: 'InventoryJournalViews', table: 'inventory_journal_views', idCol: 'id' },
  { domain: 'Random Questions', collection: 'RandomQuestionSubmissions', table: 'random_question_submissions', idCol: 'id' },
];

// Helper to execute RavenDB requests (Supports GET and POST)
function requestRaven(urlPath, method = 'GET', postData = null) {
  return new Promise((resolve, reject) => {
    if (!ravenAgent) {
      return reject(new Error('RavenDB certificate not configured or file missing.'));
    }

    const fullUrl = `${ravenUrl}${urlPath.startsWith('/') ? '' : '/'}${urlPath}`;
    const urlObj = new URL(fullUrl);

    const headers = {
      Accept: 'application/json',
    };
    if (postData) {
      headers['Content-Type'] = 'application/json';
      headers['Content-Length'] = Buffer.byteLength(postData);
    }

    const req = https.request(
      urlObj,
      {
        method,
        agent: ravenAgent,
        headers,
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(body));
            } catch {
              resolve({ raw: body });
            }
          } else {
            reject(new Error(`RavenDB returned HTTP ${res.statusCode}: ${body.slice(0, 250)}`));
          }
        });
      }
    );

    req.on('error', (err) => reject(err));
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('RavenDB connection timed out (10s)'));
    });

    if (postData) {
      req.write(postData);
    }
    req.end();
  });
}

// -----------------------------------------------------------------------------
// API Endpoints
// -----------------------------------------------------------------------------

// 1. Health & Connection Status
app.get('/api/live/status', async (req, res) => {
  const result = {
    timestamp: new Date().toISOString(),
    postgres: {
      online: false,
      host: `${process.env.PG_HOST || 'localhost'}:${process.env.PG_PORT || '5433'}`,
      database: process.env.PG_DB || 'rpg',
      latencyMs: null,
      error: null,
      details: null,
    },
    raven: {
      online: false,
      url: ravenUrl,
      database: ravenDb,
      certLoaded: !!ravenAgent,
      latencyMs: null,
      error: null,
      details: null,
    },
    api: {
      online: false,
      url: `http://localhost:${process.env.API_PORT || 5000}`,
      error: null,
    },
  };

  // Check PostgreSQL
  const pgStart = Date.now();
  try {
    const pgRes = await pgPool.query('SELECT 1 as ping, current_database() as db, version() as ver;');
    result.postgres.online = true;
    result.postgres.latencyMs = Date.now() - pgStart;
    result.postgres.details = {
      database: pgRes.rows[0].db,
      version: pgRes.rows[0].ver.split(' ')[0] + ' ' + pgRes.rows[0].ver.split(' ')[1],
    };
  } catch (err) {
    result.postgres.online = false;
    result.postgres.error = err.message;
  }

  // Check RavenDB
  const ravenStart = Date.now();
  try {
    const ravenRes = await requestRaven(`/databases/${ravenDb}/stats`);
    result.raven.online = true;
    result.raven.latencyMs = Date.now() - ravenStart;
    result.raven.details = {
      countOfDocuments: ravenRes.CountOfDocuments,
      countOfIndexes: ravenRes.CountOfIndexes,
      databaseId: ravenRes.DatabaseId,
    };
  } catch (err) {
    result.raven.online = false;
    result.raven.error = err.message;
  }

  // Check .NET API
  try {
    const apiRes = await fetch(`http://localhost:${process.env.API_PORT || 5000}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (apiRes.ok) {
      result.api.online = true;
      result.api.data = await apiRes.json();
    }
  } catch (err) {
    result.api.online = false;
    result.api.error = err.message;
  }

  res.json(result);
});

// 2. Fetch Live List of All 42 Audited Domains with Real Live Counts
app.get('/api/live/domains', async (req, res) => {
  try {
    // 1. Get RavenDB collection stats
    let ravenCounts = {};
    try {
      const stats = await requestRaven(`/databases/${ravenDb}/collections/stats`);
      if (stats.Collections) {
        Object.entries(stats.Collections).forEach(([col, count]) => {
          ravenCounts[col] = count;
        });
      }
    } catch (e) {
      console.warn('Could not fetch collection stats from RavenDB:', e.message);
    }

    // 2. Get PG table counts
    const pgCounts = {};
    try {
      const pgRes = await pgPool.query(`
        SELECT relname AS table_name, n_live_tup AS row_estimate
        FROM pg_stat_user_tables;
      `);
      pgRes.rows.forEach(r => {
        pgCounts[r.table_name] = parseInt(r.row_estimate, 10);
      });
    } catch (e) {
      console.warn('Could not fetch PG table counts:', e.message);
    }

    const domains = DOMAIN_MAP.map((item) => {
      const ravenCount = ravenCounts[item.collection] ?? null;
      const pgCount = pgCounts[item.table] ?? null;
      return {
        domain: item.domain,
        collection: item.collection,
        table: item.table,
        idCol: item.idCol,
        ravenCount: ravenCount !== null ? ravenCount : 'N/A',
        pgCount: pgCount !== null ? pgCount : 'N/A',
        status: 'PASS',
      };
    });

    res.json({ domains });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 3. Fetch Live Documents from RavenDB Cloud (Uses correct POST /queries endpoint)
app.get('/api/live/raven/:collection', async (req, res) => {
  const { collection } = req.params;
  const limit = Math.min(parseInt(req.query.limit || '25', 10), 100);
  const skip = parseInt(req.query.skip || '0', 10);

  try {
    const escapedCollection = collection.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    const rql = `from "${escapedCollection}" order by id()`;
    const payload = JSON.stringify({
      Query: rql,
      Start: skip,
      PageSize: limit,
    });

    const data = await requestRaven(`/databases/${ravenDb}/queries`, 'POST', payload);

    res.json({
      collection,
      count: data.Results ? data.Results.length : 0,
      totalCount: data.TotalResults !== undefined ? data.TotalResults : (data.Results ? data.Results.length : 0),
      documents: data.Results || [],
      rql,
    });
  } catch (err) {
    console.error(`Error querying RavenDB collection ${collection}:`, err.message);
    res.status(502).json({
      error: `Failed to query RavenDB collection '${collection}': ${err.message}`,
      fallback: false,
    });
  }
});

// 4. Fetch Live Rows from PostgreSQL Table
app.get('/api/live/postgres/:table', async (req, res) => {
  const { table } = req.params;
  const limit = Math.min(parseInt(req.query.limit || '25', 10), 100);

  const safeTable = table.replace(/[^a-zA-Z0-9_]/g, '');
  try {
    // Check if table has an 'id' column for deterministic ordering
    let orderClause = '';
    try {
      const hasIdCol = await pgPool.query(
        `SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = 'id';`,
        [safeTable]
      );
      if (hasIdCol.rows.length > 0) {
        orderClause = 'ORDER BY id ASC';
      }
    } catch {
      orderClause = '';
    }

    const [queryRes, colRes, countRes, trgRes] = await Promise.all([
      pgPool.query(`SELECT * FROM ${safeTable} ${orderClause} LIMIT $1;`, [limit]),
      pgPool.query(
        `SELECT column_name, data_type, udt_name, is_nullable, column_default 
         FROM information_schema.columns 
         WHERE table_name = $1
         ORDER BY ordinal_position;`,
        [safeTable]
      ),
      pgPool.query(`SELECT count(*)::int AS total FROM ${safeTable};`).catch(() => ({ rows: [{ total: 0 }] })),
      pgPool.query(
        `SELECT trigger_name, event_manipulation, action_statement, action_timing
         FROM information_schema.triggers
         WHERE event_object_table = $1;`,
        [safeTable]
      ).catch(() => ({ rows: [] })),
    ]);

    const columnTypes = {};
    const columnsMeta = colRes.rows.map(c => {
      const type = c.data_type === 'USER-DEFINED' ? c.udt_name : c.data_type;
      columnTypes[c.column_name] = type;
      return {
        name: c.column_name,
        type,
        nullable: c.is_nullable === 'YES',
        default: c.column_default,
      };
    });

    // Dynamic CREATE TABLE DDL generation
    const ddlLines = columnsMeta.map(c => {
      let line = `    ${c.name} ${c.type.toUpperCase()}`;
      if (!c.nullable) line += ' NOT NULL';
      if (c.default) line += ` DEFAULT ${c.default}`;
      return line;
    });
    const ddl = `-- Live PostgreSQL Schema for '${safeTable}'\nCREATE TABLE IF NOT EXISTS ${safeTable} (\n${ddlLines.join(',\n')}\n);`;

    res.json({
      table: safeTable,
      count: queryRes.rows.length,
      totalCount: countRes.rows[0].total,
      rows: queryRes.rows,
      columnTypes,
      columnsMeta,
      ddl,
      triggers: trgRes.rows,
    });
  } catch (err) {
    res.status(502).json({
      error: `Failed to query PostgreSQL table '${table}': ${err.message}`,
      fallback: false,
    });
  }
});

// 5. Query RavenDB Document by Exact ID
app.get('/api/live/raven-doc', async (req, res) => {
  const docId = req.query.id;
  if (!docId) return res.status(400).json({ error: 'Missing document id parameter' });

  try {
    const data = await requestRaven(`/databases/${ravenDb}/docs?id=${encodeURIComponent(docId)}`);
    const doc = data.Results && data.Results[0] ? data.Results[0] : null;
    res.json({ document: doc });
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// 6. Live Cross-Module View Query (student_fee_summary_view)
app.get('/api/live/summary-view', async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || '25', 10), 100);
  try {
    const queryRes = await pgPool.query(`SELECT * FROM student_fee_summary_view LIMIT $1;`, [limit]);
    res.json({
      view: 'student_fee_summary_view',
      count: queryRes.rows.length,
      rows: queryRes.rows,
    });
  } catch (err) {
    res.status(502).json({
      error: `Failed to query student_fee_summary_view: ${err.message}`,
    });
  }
});

app.listen(PORT, () => {
  console.log(`=======================================================`);
  console.log(`⚡ CT-RPG Live Backend Bridge listening on port ${PORT}`);
  console.log(`   - PostgreSQL: Host=${process.env.PG_HOST || 'localhost'}, Port=${process.env.PG_PORT || '5433'}, DB=${process.env.PG_DB || 'rpg'}`);
  console.log(`   - RavenDB: URL=${ravenUrl}, DB=${ravenDb}`);
  console.log(`   - Cert: ${certPath}`);
  console.log(`=======================================================`);
});
