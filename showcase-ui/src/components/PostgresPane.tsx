import React, { useState } from 'react';
import type { CollectionSummary } from '../types/migration';
import {
  Database,
  Copy,
  Check,
  Table2,
  Layers,
  Cpu,
  Code2,
  Zap,
  ChevronDown,
  ChevronRight,
  Eye,
  Search,
  Sparkles
} from 'lucide-react';

interface PostgresPaneProps {
  collection: CollectionSummary;
  docIndex: number;
}

const KNOWN_JSONB_COLS = new Set([
  'enrollments',
  'guardian_details',
  'installments',
  'installments_paid',
  'form_data',
  'terms',
  'claims',
  'addresses',
  'contacts',
  'attributes',
  'father',
  'mother',
  'guardian',
  'domicile',
  'fees_receivable',
  'iep',
  'documents',
  'occupations',
  'discounts',
  'fines_paid',
  'fee_adjustment',
  'attendance',
  'tags',
  'break_up',
  'sections',
  'event_dates',
  'event_message',
  'meta',
  'grading_rules',
  'customer',
  'financial_instrument',
  'order_items',
  'subscriptions',
  'hints',
  'options',
  'questions',
  'recipients',
  'change_set',
  'comments',
  'data_attributes',
  'meta_data',
  'video_links',
  'preferences',
  'profile',
  'push_notifications',
  'salaries',
  'payslips',
  'designations',
  'employment_history',
  'class_teacher',
  'course_subject_list',
  'by',
  'to',
  'section'
]);

export const PostgresPane: React.FC<PostgresPaneProps> = ({ collection, docIndex }) => {
  const [activeTab, setActiveTab] = useState<'row' | 'jsonb' | 'ddl' | 'sql' | 'triggers'>('row');
  const [copied, setCopied] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [expandedJsonbCols, setExpandedJsonbCols] = useState<Record<string, boolean>>({});
  const [columnFilter, setColumnFilter] = useState<'all' | 'jsonb' | 'scalar'>('all');
  const [columnSearch, setColumnSearch] = useState('');

  const activeRow = collection.sampleRows[docIndex] || collection.sampleRows[0];

  const handleCopy = (text: string, key?: string) => {
    navigator.clipboard.writeText(text);
    if (key) {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } else {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const toggleJsonbExpand = (key: string) => {
    setExpandedJsonbCols(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  // Merge activeRow.data and activeRow.jsonbColumns so ALL columns exist
  const allColumns: Record<string, any> = {
    ...(activeRow?.data || {}),
    ...(activeRow?.jsonbColumns || {})
  };

  const isColumnJsonb = (key: string, val: any): boolean => {
    if (activeRow?.columnTypes?.[key] === 'jsonb') return true;
    if (activeRow?.jsonbColumns && activeRow.jsonbColumns[key] !== undefined) return true;
    if (KNOWN_JSONB_COLS.has(key.toLowerCase())) return true;
    if (val !== null && typeof val === 'object') return true;
    if (typeof val === 'string' && (val.trim().startsWith('{') || val.trim().startsWith('['))) {
      try {
        const parsed = JSON.parse(val);
        return typeof parsed === 'object' && parsed !== null;
      } catch {
        return false;
      }
    }
    return false;
  };

  const getParsedJsonValue = (val: any) => {
    if (val !== null && typeof val === 'object') return val;
    if (typeof val === 'string' && (val.trim().startsWith('{') || val.trim().startsWith('['))) {
      try {
        return JSON.parse(val);
      } catch {
        return val;
      }
    }
    return val;
  };

  // Collect all JSONB columns for the dedicated JSONB tab
  const allJsonbColumns: Record<string, any> = {
    ...(activeRow?.jsonbColumns || {})
  };

  Object.entries(allColumns).forEach(([k, v]) => {
    if (isColumnJsonb(k, v) && allJsonbColumns[k] === undefined) {
      allJsonbColumns[k] = getParsedJsonValue(v);
    }
  });

  const jsonbKeyCount = Object.keys(allJsonbColumns).length;
  const totalColumnCount = Object.keys(allColumns).length;
  const scalarKeyCount = Math.max(0, totalColumnCount - jsonbKeyCount);

  // Filter columns according to selected pill & search box
  const filteredColumns = Object.entries(allColumns).filter(([key, val]) => {
    const isJson = isColumnJsonb(key, val);

    if (columnFilter === 'jsonb' && !isJson) return false;
    if (columnFilter === 'scalar' && isJson) return false;

    if (columnSearch.trim()) {
      const q = columnSearch.toLowerCase();
      const valStr = typeof val === 'object' ? JSON.stringify(val).toLowerCase() : String(val).toLowerCase();
      return key.toLowerCase().includes(q) || valStr.includes(q);
    }

    return true;
  });

  return (
    <div className="pane postgres-pane">
      <div className="pane-header">
        <div className="pane-title-group">
          <div className="pane-icon-badge pg-theme">
            <Database size={16} />
          </div>
          <div>
            <div className="pane-title">
              PostgreSQL 16 <span className="pane-sub-type">(Target • Relational + JSONB)</span>
            </div>
            <div className="pane-collection-name">
              Table / View: <span className="highlight-tag pg">{collection.postgresTable}</span>
            </div>
          </div>
        </div>

        <div className="pane-meta-pill pg-pill">
          <span>Row ID:</span>
          <strong>{activeRow?.id?.slice(0, 18)}...</strong>
        </div>
      </div>

      <div className="pane-subtabs">
        <button
          className={`pane-subtab ${activeTab === 'row' ? 'active' : ''}`}
          onClick={() => setActiveTab('row')}
        >
          <Table2 size={14} /> Relational Data
        </button>
        <button
          className={`pane-subtab ${activeTab === 'jsonb' ? 'active' : ''}`}
          onClick={() => setActiveTab('jsonb')}
        >
          <Layers size={14} /> JSONB Lateral ({jsonbKeyCount})
        </button>
        <button
          className={`pane-subtab ${activeTab === 'ddl' ? 'active' : ''}`}
          onClick={() => setActiveTab('ddl')}
        >
          <Code2 size={14} /> Schema & DDL
        </button>
        <button
          className={`pane-subtab ${activeTab === 'sql' ? 'active' : ''}`}
          onClick={() => setActiveTab('sql')}
        >
          <Cpu size={14} /> SQL Query
        </button>
        <button
          className={`pane-subtab ${activeTab === 'triggers' ? 'active' : ''}`}
          onClick={() => setActiveTab('triggers')}
        >
          <Zap size={14} /> Triggers & GIN
        </button>

        <div className="subtab-action">
          <button
            className="copy-btn pg-copy"
            onClick={() => handleCopy(JSON.stringify(allColumns, null, 2))}
            title="Copy row data"
          >
            {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>

      <div className="pane-content-body">
        {activeTab === 'row' && (
          <div className="relational-grid-container">
            {/* Column Filter Toolbar */}
            <div className="pg-table-filter-bar">
              <div className="pg-filter-pills">
                <button
                  className={`pg-filter-btn ${columnFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setColumnFilter('all')}
                >
                  All Columns ({totalColumnCount})
                </button>
                <button
                  className={`pg-filter-btn jsonb-btn ${columnFilter === 'jsonb' ? 'active' : ''}`}
                  onClick={() => setColumnFilter('jsonb')}
                >
                  <Sparkles size={12} className="text-info" />
                  JSONB Columns ({jsonbKeyCount})
                </button>
                <button
                  className={`pg-filter-btn ${columnFilter === 'scalar' ? 'active' : ''}`}
                  onClick={() => setColumnFilter('scalar')}
                >
                  Scalar Only ({scalarKeyCount})
                </button>
              </div>

              <div className="pg-col-search">
                <Search size={13} />
                <input
                  type="text"
                  placeholder="Filter columns (e.g. enrollments, father)..."
                  value={columnSearch}
                  onChange={e => setColumnSearch(e.target.value)}
                />
              </div>
            </div>

            <table className="pg-data-table">
              <thead>
                <tr>
                  <th style={{ width: '28%' }}>Column (snake_case)</th>
                  <th style={{ width: '52%' }}>Value</th>
                  <th style={{ width: '20%' }}>PostgreSQL Type</th>
                </tr>
              </thead>
              <tbody>
                {filteredColumns.length > 0 ? (
                  filteredColumns.map(([key, rawVal]) => {
                    const isJsonb = isColumnJsonb(key, rawVal);
                    const val = isJsonb ? getParsedJsonValue(rawVal) : rawVal;
                    const isExpanded = !!expandedJsonbCols[key];

                    return (
                      <tr key={key} className={isJsonb ? 'jsonb-row' : ''}>
                        <td className="col-name font-mono">
                          {isJsonb && (
                            <span className="jsonb-indicator-tag" title="Native PostgreSQL JSONB column indexed with GIN">
                              <Layers size={12} className="inline-jsonb-icon text-info" />
                              JSONB
                            </span>
                          )}
                          <span className={isJsonb ? 'text-info font-bold' : ''}>{key}</span>
                        </td>
                        <td className="col-value">
                          {isJsonb ? (
                            <div className="jsonb-value-container">
                              {val === null || val === undefined ? (
                                <span className="jsonb-null-badge">null (empty jsonb)</span>
                              ) : (
                                <>
                                  <div className="jsonb-controls-row">
                                    <button
                                      className="jsonb-toggle-btn"
                                      onClick={() => toggleJsonbExpand(key)}
                                    >
                                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                      <span className="jsonb-count-label">
                                        {Array.isArray(val)
                                          ? `JSONB Array [${val.length} item${val.length === 1 ? '' : 's'}]`
                                          : `JSONB Object {${Object.keys(val || {}).length} prop${Object.keys(val || {}).length === 1 ? '' : 's'}}`}
                                      </span>
                                      <Eye size={12} className="eye-icon" />
                                    </button>

                                    <button
                                      className="jsonb-copy-btn"
                                      onClick={() => handleCopy(JSON.stringify(val, null, 2), key)}
                                      title="Copy JSON payload"
                                    >
                                      {copiedKey === key ? (
                                        <Check size={11} className="text-success" />
                                      ) : (
                                        <Copy size={11} />
                                      )}
                                      <span>{copiedKey === key ? 'Copied' : 'JSON'}</span>
                                    </button>
                                  </div>

                                  {isExpanded && (
                                    <pre className="jsonb-inline-code">
                                      <code>{JSON.stringify(val, null, 2)}</code>
                                    </pre>
                                  )}
                                </>
                              )}
                            </div>
                          ) : typeof val === 'boolean' ? (
                            <span className={`boolean-badge ${val ? 'true' : 'false'}`}>
                              {val ? 'TRUE' : 'FALSE'}
                            </span>
                          ) : val === null || val === undefined ? (
                            <span className="text-muted">null</span>
                          ) : (
                            <span className="font-mono text-break">{String(val)}</span>
                          )}
                        </td>
                        <td className="col-type">
                          {isJsonb ? (
                            <span className="type-badge-jsonb" title="GIN Indexed Binary JSON">
                              JSONB (GIN)
                            </span>
                          ) : activeRow?.columnTypes?.[key] ? (
                            <span className="type-badge-explicit">{activeRow.columnTypes[key].toUpperCase()}</span>
                          ) : key.includes('id') ? (
                            <span className="type-badge-uuid">UUID</span>
                          ) : key.includes('date') || key.includes('on') ? (
                            <span className="type-badge-time">TIMESTAMPTZ</span>
                          ) : typeof val === 'number' ? (
                            <span className="type-badge-numeric">NUMERIC</span>
                          ) : typeof val === 'boolean' ? (
                            <span className="type-badge-bool">BOOLEAN</span>
                          ) : (
                            <span className="text-muted">VARCHAR</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={3} className="empty-filter-cell">
                      No columns match the current filter "{columnSearch}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'jsonb' && (
          <div className="jsonb-container">
            <div className="jsonb-info-callout">
              <Layers size={16} className="text-info" />
              <div>
                <strong>PostgreSQL JSONB Architecture:</strong> All document arrays and sub-objects from RavenDB
                are mapped into native PostgreSQL <code>JSONB</code> columns. These support direct indexing via <code>GIN</code> (Generalized Inverted Index) and relational exploding via <code>CROSS JOIN LATERAL jsonb_array_elements(...)</code>.
              </div>
            </div>

            {jsonbKeyCount > 0 ? (
              Object.entries(allJsonbColumns).map(([colName, rawColVal]) => {
                const colVal = getParsedJsonValue(rawColVal);
                const isArray = Array.isArray(colVal);
                const isNull = colVal === null || colVal === undefined;

                return (
                  <div key={colName} className="jsonb-card">
                    <div className="jsonb-card-header">
                      <div className="jsonb-header-left">
                        <Layers size={15} className="text-info" />
                        <span className="jsonb-col-title">Column: <code>{colName}</code></span>
                      </div>
                      <div className="jsonb-header-right">
                        <span className="jsonb-badge">
                          {isNull
                            ? 'JSONB (null / empty)'
                            : isArray
                            ? `JSONB Array (${colVal.length} elements)`
                            : `JSONB Object (${Object.keys(colVal || {}).length} properties)`} • GIN Indexed
                        </span>
                        <button
                          className="copy-btn-mini"
                          onClick={() => handleCopy(JSON.stringify(colVal, null, 2), `tab-${colName}`)}
                          title="Copy JSON"
                        >
                          {copiedKey === `tab-${colName}` ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                          <span>{copiedKey === `tab-${colName}` ? 'Copied' : 'Copy'}</span>
                        </button>
                      </div>
                    </div>

                    {/* Exploded LATERAL View for Arrays */}
                    {isArray && colVal.length > 0 && typeof colVal[0] === 'object' && (
                      <div className="lateral-exploded-box">
                        <div className="lateral-box-header">
                          <Table2 size={13} className="text-info" />
                          <span>LATERAL Extraction: <code>CROSS JOIN LATERAL jsonb_array_elements({colName}) AS item</code></span>
                        </div>
                        <div className="lateral-table-scroll">
                          <table className="lateral-sub-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                {Object.keys(colVal[0]).slice(0, 8).map((attrKey) => (
                                  <th key={attrKey} className="font-mono">{attrKey}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {colVal.map((item: any, itemIdx: number) => (
                                <tr key={itemIdx}>
                                  <td className="item-idx font-mono">{itemIdx + 1}</td>
                                  {Object.keys(colVal[0]).slice(0, 8).map((attrKey) => (
                                    <td key={attrKey} className="font-mono text-small">
                                      {typeof item[attrKey] === 'object'
                                        ? JSON.stringify(item[attrKey])
                                        : String(item[attrKey] ?? '')}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <div className="jsonb-raw-header">Raw JSONB Payload:</div>
                    <pre className="jsonb-code">
                      <code>{JSON.stringify(colVal, null, 2)}</code>
                    </pre>
                  </div>
                );
              })
            ) : (
              <div className="jsonb-empty">
                <p>This table uses pure relational scalar columns. Nested arrays are managed via relational foreign keys or views.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'ddl' && (
          <div className="ddl-container">
            <div className="code-viewer-container">
              <pre className="code-block sql-syntax">
                <code>{collection.ddl}</code>
              </pre>
            </div>
          </div>
        )}

        {activeTab === 'sql' && (
          <div className="sql-container">
            <div className="query-box">
              <div className="query-header">Active Row SQL Query</div>
              <div className="query-code">{activeRow?.sqlQuery || `SELECT * FROM ${collection.postgresTable} LIMIT 10;`}</div>
            </div>
            <div className="query-notes">
              Executed with parameterized UUID lookups and native LATERAL projections in PostgreSQL 16.
            </div>
          </div>
        )}

        {activeTab === 'triggers' && (
          <div className="triggers-container">
            <div className="trigger-card">
              <div className="trigger-header">
                <Zap size={16} className="text-warning" />
                <span>Active Triggers & Functions</span>
              </div>
              <pre className="code-block sql-syntax">
                <code>{collection.triggers || `-- Automated timestamp & audit triggers active for ${collection.postgresTable}\n-- Schema maintains updated_at and audit logs synchronously`}</code>
              </pre>
            </div>

            <div className="indexes-card">
              <div className="indexes-header">
                <Layers size={16} className="text-info" />
                <span>GIN & B-Tree Indexes</span>
              </div>
              <ul className="index-list">
                {collection.indexes?.map((idxName, i) => (
                  <li key={i} className="index-item">
                    <span className="index-bullet">⚡</span>
                    <code>{idxName}</code>
                  </li>
                )) || (
                  <li className="index-item">
                    <span className="index-bullet">⚡</span>
                    <code>idx_{collection.postgresTable}_pkey (PRIMARY KEY)</code>
                  </li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
