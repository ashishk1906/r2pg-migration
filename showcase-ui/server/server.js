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
  port: parseInt(process.env.PG_PORT || '5432', 10),
  database: process.env.PG_DB || '',
  user: process.env.PG_USER || 'postgres',
  password: process.env.PG_PASSWORD || '',
  connectionTimeoutMillis: 3000,
  query_timeout: 8000,
});

// 2. RavenDB HTTPS Client Agent with .pfx Certificate
const ravenUrl = (process.env.RAVEN_URL || '').replace(/\/+$/, '');
const ravenDb = process.env.RAVEN_DB || '';
const rawCertPath = process.env.RAVEN_CERT_FILE || '';
const certPath = rawCertPath
  ? (path.isAbsolute(rawCertPath)
      ? rawCertPath
      : path.resolve(__dirname, '../../scripts', rawCertPath))
  : '';

let ravenAgent = null;
if (certPath && fs.existsSync(certPath)) {
  try {
    const pfxBuffer = fs.readFileSync(certPath);
    ravenAgent = new https.Agent({
      pfx: pfxBuffer,
      passphrase: process.env.RAVEN_CERT_PASSWORD || '',
      rejectUnauthorized: process.env.RAVEN_INSECURE === 'true' ? false : true,
      timeout: 10000,
    });
    console.log(`[RavenDB] Client certificate loaded successfully.`);
  } catch (err) {
    console.error(`[RavenDB] Failed to load certificate: ${err.message}`);
  }
} else if (rawCertPath) {
  console.warn(`[RavenDB] Certificate file not found at: ${certPath}`);
}

// Dynamic title formatter: converts snake_case or PascalCase to human-readable title
function formatDomainTitle(name) {
  if (!name) return 'Unknown';
  return name
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
    .trim();
}

// Normalized alphanumeric key for dynamic pairing without hardcoding
function toMatchKey(str) {
  if (!str) return '';
  let k = str.toLowerCase().replace(/[^a-z0-9]/g, '');
  k = k.replace(/transactions?/g, 'tx');
  k = k.replace(/organizations?/g, 'org');
  k = k.replace(/txes$/, 'tx').replace(/txs$/, 'tx');
  k = k.replace(/matrices$/, 'matrix');
  k = k.replace(/ies$/, 'y');
  k = k.replace(/s$/, '');
  return k;
}

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
      host: `${process.env.PG_HOST || 'localhost'}:${process.env.PG_PORT || '5432'}`,
      database: process.env.PG_DB || '',
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

// 2. Fetch Live Discovered Collections and Tables with Real Database Counts
app.get('/api/live/domains', async (req, res) => {
  try {
    // 1. Get Live RavenDB collections
    let ravenCounts = {};
    let isRavenConnected = false;
    try {
      const stats = await requestRaven(`/databases/${ravenDb}/collections/stats`);
      if (stats && stats.Collections) {
        isRavenConnected = true;
        Object.entries(stats.Collections).forEach(([col, count]) => {
          // Ignore RavenDB internal system collections (e.g. @hilo, @empty, Raven/*)
          if (!col.startsWith('@') && !col.toLowerCase().startsWith('raven/')) {
            ravenCounts[col] = count;
          }
        });
      }
    } catch (e) {
      console.warn('Could not fetch collection stats from RavenDB:', e.message);
    }

    // 2. Get Live PG table list and row counts dynamically from information_schema
    const pgTables = [];
    let isPgConnected = false;
    try {
      const pgRes = await pgPool.query(`
        SELECT 
          t.table_name,
          COALESCE(s.n_live_tup, 0)::int AS row_estimate
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_schema = 'public' 
          AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name ASC;
      `);
      isPgConnected = true;
      pgRes.rows.forEach(r => {
        pgTables.push({
          table: r.table_name,
          count: r.row_estimate,
        });
      });
    } catch (e) {
      console.warn('Could not fetch PG table counts:', e.message);
    }

    // 3. Dynamic pairing of tables and collections without ANY hardcoding
    const domains = [];
    const matchedRavenCollections = new Set();
    const ravenKeys = Object.keys(ravenCounts);

    // Build map of RavenDB match keys
    const ravenKeyMap = new Map();
    ravenKeys.forEach(col => {
      ravenKeyMap.set(toMatchKey(col), col);
      ravenKeyMap.set(toMatchKey(col).replace(/s$/, ''), col);
      ravenKeyMap.set(toMatchKey(col).replace(/es$/, ''), col);
    });

    // Pair all live PostgreSQL tables
    pgTables.forEach(pt => {
      const pKey = toMatchKey(pt.table);
      let matchedCol = ravenKeyMap.get(pKey) || 
                       ravenKeyMap.get(pKey.replace(/s$/, '')) || 
                       ravenKeyMap.get(pKey + 's') || 
                       ravenKeyMap.get(pKey + 'es');

      if (!matchedCol) {
        for (const col of ravenKeys) {
          const cKey = toMatchKey(col);
          if (cKey.includes(pKey) || pKey.includes(cKey)) {
            matchedCol = col;
            break;
          }
        }
      }

      if (matchedCol) {
        matchedRavenCollections.add(matchedCol);
      }

      const ravenCount = matchedCol ? (ravenCounts[matchedCol] ?? (isRavenConnected ? 0 : 'N/A')) : (isRavenConnected ? 0 : 'N/A');
      const pgCount = pt.count;
      const isMatch = isRavenConnected && isPgConnected && typeof ravenCount === 'number' && ravenCount === pgCount && pgCount > 0;

      domains.push({
        domain: formatDomainTitle(matchedCol || pt.table),
        collection: matchedCol || formatDomainTitle(pt.table).replace(/\s+/g, ''),
        table: pt.table,
        idCol: 'id',
        ravenCount,
        pgCount,
        status: isMatch ? 'PASS' : 'PENDING',
      });
    });

    // Add any RavenDB collections that did not match a PG table
    ravenKeys.forEach(col => {
      if (!matchedRavenCollections.has(col)) {
        const inferredTable = col.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
        domains.push({
          domain: formatDomainTitle(col),
          collection: col,
          table: inferredTable,
          idCol: 'id',
          ravenCount: ravenCounts[col],
          pgCount: isPgConnected ? 0 : 'N/A',
          status: 'PENDING',
        });
      }
    });

    res.json({ domains });
  } catch (err) {
    res.status(500).json({ error: err.message, domains: [] });
  }
});

// 3. Fetch Live Documents from RavenDB Cloud (Uses correct POST /queries endpoint)
app.get('/api/live/raven/:collection', async (req, res) => {
  const { collection } = req.params;
  const isAll = req.query.limit === 'all' || !req.query.limit;
  const limit = isAll ? 50000 : parseInt(req.query.limit, 10);
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
  const isAll = req.query.limit === 'all' || !req.query.limit;
  let limitClause = '';
  const queryParams = [];

  if (!isAll && req.query.limit) {
    queryParams.push(parseInt(req.query.limit, 10));
    limitClause = `LIMIT $1`;
  }

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
      pgPool.query(`SELECT * FROM ${safeTable} ${orderClause} ${limitClause};`, queryParams),
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

process.on('uncaughtException', (err) => {
  console.warn('[Server Warning] Uncaught exception:', err.message);
});
process.on('unhandledRejection', (reason) => {
  console.warn('[Server Warning] Unhandled rejection:', reason);
});

app.listen(PORT, () => {
  console.log(`=======================================================`);
  console.log(`⚡ CT-RPG Live Backend Bridge listening on port ${PORT}`);
  console.log(`   - PostgreSQL: Host=${process.env.PG_HOST || 'localhost'}, Port=${process.env.PG_PORT || '5432'}, DB=${process.env.PG_DB || '(from .env)'}`);
  console.log(`   - RavenDB: Configured=${Boolean(ravenUrl && ravenDb)}, CertLoaded=${Boolean(ravenAgent)}`);
  console.log(`=======================================================`);
});
