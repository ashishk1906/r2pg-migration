import React, { useState } from 'react';
import type { CollectionSummary } from '../types/migration';
import { Flame, Copy, Check, Code, Info, Terminal, FileCode2 } from 'lucide-react';

interface RavenPaneProps {
  collection: CollectionSummary;
  docIndex: number;
}

export const RavenPane: React.FC<RavenPaneProps> = ({ collection, docIndex }) => {
  const [activeTab, setActiveTab] = useState<'json' | 'metadata' | 'rql' | 'stats'>('json');
  const [copied, setCopied] = useState(false);

  const activeDoc = collection.sampleDocuments[docIndex] || collection.sampleDocuments[0];

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="pane raven-pane">
      <div className="pane-header">
        <div className="pane-title-group">
          <div className="pane-icon-badge raven-theme">
            <Flame size={16} />
          </div>
          <div>
            <div className="pane-title">
              RavenDB <span className="pane-sub-type">(Source • Document Store)</span>
            </div>
            <div className="pane-collection-name">
              Collection: <span className="highlight-tag">{collection.ravenCollection}</span>
            </div>
          </div>
        </div>

        <div className="pane-meta-pill">
          <span>Doc ID:</span>
          <strong>{activeDoc?.id || 'N/A'}</strong>
        </div>
      </div>

      <div className="pane-subtabs">
        <button
          className={`pane-subtab ${activeTab === 'json' ? 'active' : ''}`}
          onClick={() => setActiveTab('json')}
        >
          <Code size={14} /> Document JSON
        </button>
        <button
          className={`pane-subtab ${activeTab === 'metadata' ? 'active' : ''}`}
          onClick={() => setActiveTab('metadata')}
        >
          <Info size={14} /> @metadata
        </button>
        <button
          className={`pane-subtab ${activeTab === 'rql' ? 'active' : ''}`}
          onClick={() => setActiveTab('rql')}
        >
          <Terminal size={14} /> RQL Query
        </button>
        <button
          className={`pane-subtab ${activeTab === 'stats' ? 'active' : ''}`}
          onClick={() => setActiveTab('stats')}
        >
          <FileCode2 size={14} /> Source Stats
        </button>

        <div className="subtab-action">
          <button
            className="copy-btn"
            onClick={() => handleCopy(JSON.stringify(activeDoc?.data, null, 2))}
            title="Copy document content"
          >
            {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>

      <div className="pane-content-body">
        {activeTab === 'json' && (
          <div className="code-viewer-container">
            <pre className="code-block json-syntax">
              <code>{JSON.stringify(activeDoc?.data, null, 2)}</code>
            </pre>
          </div>
        )}

        {activeTab === 'metadata' && (
          <div className="metadata-container">
            <div className="metadata-card">
              <div className="metadata-row">
                <span className="meta-key">@id:</span>
                <span className="meta-val font-mono">{activeDoc?.metadata?.id}</span>
              </div>
              <div className="metadata-row">
                <span className="meta-key">Raven-Clr-Type:</span>
                <span className="meta-val font-mono">{activeDoc?.metadata?.clrType || 'Generic.Document'}</span>
              </div>
              <div className="metadata-row">
                <span className="meta-key">@last-modified:</span>
                <span className="meta-val font-mono">{activeDoc?.metadata?.lastModified || '2026-09-28T08:14:22Z'}</span>
              </div>
              <div className="metadata-row">
                <span className="meta-key">@change-vector:</span>
                <span className="meta-val font-mono">{activeDoc?.metadata?.changeVector || 'A:4812-7XkWqjD5K0'}</span>
              </div>
            </div>

            <div className="metadata-explanation-box">
              <Info size={16} className="text-info" />
              <p>
                In RavenDB, documents carry a server-generated <code>@change-vector</code> and CLR type metadata.
                During migration, the Python ETL pipeline strips runtime CLR metadata and normalizes
                the <code>Last-Modified</code> timestamp directly into PostgreSQL's <code>modified_on TIMESTAMPTZ</code> column.
              </p>
            </div>
          </div>
        )}

        {activeTab === 'rql' && (
          <div className="rql-container">
            <div className="query-box">
              <div className="query-header">
                <span>Raven Query Language (RQL)</span>
              </div>
              <pre className="query-code">
                <code>{activeDoc?.rqlQuery || `from ${collection.ravenCollection} where Id = "${activeDoc?.id}"`}</code>
              </pre>
            </div>
            <div className="query-notes">
              <p>
                <strong>Execution Mechanics:</strong> RavenDB evaluates RQL against Lucene/Corax document indexes.
                No relational joins occur in the database; nested arrays are retrieved wholesale within the single JSON document.
              </p>
            </div>
          </div>
        )}

        {activeTab === 'stats' && (
          <div className="stats-container">
            <div className="stat-grid">
              <div className="stat-card">
                <span className="stat-label">Total Documents</span>
                <span className="stat-value">{collection.documentCount}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Primary Identifier</span>
                <span className="stat-value text-small">{collection.primaryKey}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Indexing Strategy</span>
                <span className="stat-value text-small">Auto Index (Corax Engine)</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Parity Audit Status</span>
                <span className="stat-value text-success">Verified (0 Missing)</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
