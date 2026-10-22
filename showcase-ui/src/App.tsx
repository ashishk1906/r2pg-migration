import { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { DomainSelector } from './components/DomainSelector';
import { ParityBar } from './components/ParityBar';
import { RavenPane } from './components/RavenPane';
import { PostgresPane } from './components/PostgresPane';
import { AiChat } from './components/AiChat';
import { ParityAuditModal } from './components/ParityAuditModal';
import type { CollectionSummary, RavenDocument, PostgresRow } from './types/migration';

interface LiveStatus {
  postgres: { online: boolean; latencyMs?: number };
  raven: { online: boolean; latencyMs?: number };
  api: { online: boolean };
}

// Helper to dynamically resolve table and collection names from live database domains
function resolveDomain(id: string, liveDomains: any[] = []) {
  const cleanId = (id || '').toLowerCase().trim();

  const found = liveDomains.find(
    d => (d.table && d.table.toLowerCase() === cleanId) ||
         (d.collection && d.collection.toLowerCase() === cleanId) ||
         (d.domain && d.domain.toLowerCase() === cleanId)
  );

  if (found) {
    return {
      domainDef: found,
      currentTableName: found.table || cleanId,
      currentCollectionName: found.collection || cleanId,
    };
  }

  return {
    domainDef: { domain: id || 'None', collection: id || '', table: id || '' },
    currentTableName: id,
    currentCollectionName: id,
  };
}

const initialEmptyCollection: CollectionSummary = {
  id: '',
  name: 'No Collection Selected',
  ravenCollection: '',
  postgresTable: '',
  documentCount: 0,
  rowCount: 0,
  matchedCount: 0,
  missingInPg: 0,
  extraInPg: 0,
  fieldMismatches: 0,
  status: 'PENDING',
  primaryKey: 'id',
  sampleDocuments: [],
  sampleRows: [],
  ddl: '',
  triggers: '',
  indexes: [],
};

export function App() {
  const [selectedCollectionId, setSelectedCollectionId] = useState<string>('');
  const [selectedDocIndex, setSelectedDocIndex] = useState<number>(0);
  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [isAuditModalOpen, setIsAuditModalOpen] = useState<boolean>(false);
  const [isLoadingDomain, setIsLoadingDomain] = useState<boolean>(false);

  // Live Connection & Data State (100% Dynamic from PostgreSQL & RavenDB)
  const [liveStatus, setLiveStatus] = useState<LiveStatus | null>(null);
  const [activeCollectionData, setActiveCollectionData] = useState<CollectionSummary>(initialEmptyCollection);
  const [liveDomainsStats, setLiveDomainsStats] = useState<any[]>([]);
  const domainCacheRef = useRef<Record<string, CollectionSummary>>({});

  // 1. Poll live backend status every 8 seconds
  useEffect(() => {
    let isMounted = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch('http://localhost:3001/api/live/status');
        if (res.ok && isMounted) {
          const data = await res.json();
          setLiveStatus({
            postgres: { online: data.postgres.online, latencyMs: data.postgres.latencyMs },
            raven: { online: data.raven.online, latencyMs: data.raven.latencyMs },
            api: { online: data.api.online },
          });
        }
      } catch {
        if (isMounted) {
          setLiveStatus({
            postgres: { online: false },
            raven: { online: false },
            api: { online: false },
          });
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 8000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // 2. Fetch live domains overview
  useEffect(() => {
    let isMounted = true;
    const fetchDomains = async () => {
      try {
        const res = await fetch('http://localhost:3001/api/live/domains');
        if (res.ok && isMounted) {
          const data = await res.json();
          if (data.domains && data.domains.length > 0) {
            setLiveDomainsStats(data.domains);
            setSelectedCollectionId(prev => {
              if (prev && data.domains.some((d: any) => d.table === prev || d.collection === prev)) {
                return prev;
              }
              return data.domains[0].table || data.domains[0].collection;
            });
          } else {
            setLiveDomainsStats([]);
          }
        }
      } catch (err) {
        if (isMounted) setLiveDomainsStats([]);
      }
    };
    fetchDomains();
    const interval = setInterval(fetchDomains, 8000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // 3. Fetch real live documents and PostgreSQL rows whenever selected domain changes
  useEffect(() => {
    let isCancelled = false;
    if (!selectedCollectionId) {
      setActiveCollectionData(initialEmptyCollection);
      return;
    }

    const { domainDef, currentTableName, currentCollectionName } = resolveDomain(selectedCollectionId, liveDomainsStats);

    const cacheKey = currentTableName;
    if (domainCacheRef.current[cacheKey]) {
      setActiveCollectionData(domainCacheRef.current[cacheKey]);
      setIsLoadingDomain(false);
    }

    const fetchLiveCollection = async () => {
      try {
        const [pgRes, ravenRes] = await Promise.allSettled([
          fetch(`http://localhost:3001/api/live/postgres/${currentTableName}?limit=all`),
          fetch(`http://localhost:3001/api/live/raven/${encodeURIComponent(currentCollectionName)}?limit=all`),
        ]);

        let liveRows: PostgresRow[] = [];
        let liveDocs: RavenDocument[] = [];
        let ddl = '';
        let triggers = '';
        let totalDocsCount = 0;
        let totalRowsCount = 0;

        // Process Live PostgreSQL Rows
        if (pgRes.status === 'fulfilled' && pgRes.value.ok) {
          const pgData = await pgRes.value.json();
          totalRowsCount = pgData.totalCount !== undefined ? pgData.totalCount : pgData.rows?.length || 0;
          if (pgData.ddl) ddl = pgData.ddl;
          if (pgData.triggers && pgData.triggers.length > 0) {
            triggers = pgData.triggers
              .map((t: any) => `-- Trigger: ${t.trigger_name}\n${t.action_timing} ${t.event_manipulation} ON ${currentTableName}\n${t.action_statement};`)
              .join('\n\n');
          }

          if (pgData.rows && pgData.rows.length > 0) {
            const jsonbColNames = new Set(
              Object.entries(pgData.columnTypes || {})
                .filter(([_, t]) => t === 'jsonb')
                .map(([col]) => col)
            );

            liveRows = pgData.rows.map((row: any) => {
              const detectedJsonb: Record<string, any> = {};
              for (const key in row) {
                const val = row[key];
                if ((val !== null && typeof val === 'object') || jsonbColNames.has(key)) {
                  detectedJsonb[key] = val;
                }
              }

              return {
                id: row.id || row.student_id || row.fee_id || row.fee_transaction_id || 'unknown',
                data: row,
                jsonbColumns: detectedJsonb,
                columnTypes: pgData.columnTypes || {},
                sqlQuery: `SELECT * FROM ${currentTableName} WHERE id = '${row.id}';`,
              };
            });
          }
        }

        // Process Live RavenDB Documents
        if (ravenRes.status === 'fulfilled' && ravenRes.value.ok) {
          const rData = await ravenRes.value.json();
          totalDocsCount = rData.totalCount !== undefined ? rData.totalCount : rData.documents?.length || 0;

          if (rData.documents && rData.documents.length > 0) {
            liveDocs = rData.documents.map((doc: any, i: number) => ({
              id: doc['@metadata']?.['@id'] || `${currentCollectionName}/${i}`,
              metadata: {
                id: doc['@metadata']?.['@id'] || `${currentCollectionName}/${i}`,
                clrType: doc['@metadata']?.['Raven-Clr-Type'] || `CampusTrack.Domain.${currentCollectionName}`,
                lastModified: doc['@metadata']?.['@last-modified'],
                changeVector: doc['@metadata']?.['@change-vector'],
              },
              data: doc,
              rqlQuery: rData.rql ? `${rData.rql} where id() = "${doc['@metadata']?.['@id']}"` : `from "${currentCollectionName}"`,
            }));
          }
        }

        if (!isCancelled) {
          const newData: CollectionSummary = {
            id: currentTableName,
            name: domainDef.domain,
            ravenCollection: currentCollectionName,
            postgresTable: currentTableName,
            documentCount: totalDocsCount,
            rowCount: totalRowsCount,
            matchedCount: Math.min(totalDocsCount, totalRowsCount),
            missingInPg: Math.max(0, totalDocsCount - totalRowsCount),
            extraInPg: Math.max(0, totalRowsCount - totalDocsCount),
            fieldMismatches: 0,
            status: totalDocsCount === totalRowsCount && totalDocsCount > 0 ? 'PASS' : (totalDocsCount === 0 && totalRowsCount === 0 ? 'PENDING' : 'FAIL'),
            primaryKey: 'id',
            sampleDocuments: liveDocs,
            sampleRows: liveRows,
            ddl,
            triggers,
            indexes: [`idx_${currentTableName}_id (B-Tree)`],
          };

          domainCacheRef.current[cacheKey] = newData;
          setActiveCollectionData(newData);
        }
      } catch (err) {
        console.error('Failed to query live database data:', err);
      } finally {
        if (!isCancelled) {
          setIsLoadingDomain(false);
        }
      }
    };

    fetchLiveCollection();
    return () => {
      isCancelled = true;
    };
  }, [selectedCollectionId, liveDomainsStats]);

  const currentCollection = activeCollectionData;

  const handleRunAudit = () => {
    setIsAuditing(true);
    setTimeout(() => {
      setIsAuditing(false);
    }, 1200);
  };

  const isDatabasesOnline = Boolean(liveStatus?.postgres.online && liveStatus?.raven.online);

  // Dynamic domains derived strictly from live discovered domains (filtering out RavenDB @ system collections)
  const validLiveDomains = liveDomainsStats.filter(d => !d.collection?.startsWith('@'));

  const dynamicTabs: CollectionSummary[] = validLiveDomains.map(tab => {
    const docCount = typeof tab.ravenCount === 'number' ? tab.ravenCount : 0;
    const rowCount = typeof tab.pgCount === 'number' ? tab.pgCount : 0;

    return {
      id: tab.table || tab.collection,
      name: tab.domain || tab.collection,
      ravenCollection: tab.collection,
      postgresTable: tab.table,
      documentCount: isDatabasesOnline ? docCount : 0,
      rowCount: isDatabasesOnline ? rowCount : 0,
      matchedCount: isDatabasesOnline ? Math.min(docCount, rowCount) : 0,
      missingInPg: isDatabasesOnline ? Math.max(0, docCount - rowCount) : 0,
      extraInPg: isDatabasesOnline ? Math.max(0, rowCount - docCount) : 0,
      fieldMismatches: 0,
      status: isDatabasesOnline && docCount > 0 && docCount === rowCount ? 'PASS' : 'PENDING',
      primaryKey: tab.idCol || 'id',
      sampleDocuments: [],
      sampleRows: [],
      ddl: '',
      triggers: '',
      indexes: [],
    };
  });

  return (
    <div className="app-layout">
      {/* Top Header */}
      <Header
        stats={{
          timestampUtc: new Date().toISOString(),
          collectionsAuditedCount: isDatabasesOnline && validLiveDomains.length > 0 ? validLiveDomains.length : 0,
          totalDocumentsInRaven: isDatabasesOnline ? (validLiveDomains.reduce((acc, d) => acc + (typeof d.ravenCount === 'number' ? d.ravenCount : 0), 0) || currentCollection.documentCount) : 0,
          totalRowsInPostgres: isDatabasesOnline ? (validLiveDomains.reduce((acc, d) => acc + (typeof d.pgCount === 'number' ? d.pgCount : 0), 0) || currentCollection.rowCount) : 0,
          totalMatchedIds: isDatabasesOnline ? (validLiveDomains.reduce((acc, d) => acc + Math.min(typeof d.ravenCount === 'number' ? d.ravenCount : 0, typeof d.pgCount === 'number' ? d.pgCount : 0), 0) || Math.min(currentCollection.documentCount, currentCollection.rowCount)) : 0,
          overallStatus: (isDatabasesOnline && currentCollection.documentCount > 0) ? 'PASS' : 'PENDING',
        }}
        onRunAudit={handleRunAudit}
        onOpenAuditModal={() => setIsAuditModalOpen(true)}
        isAuditing={isAuditing}
        liveStatus={liveStatus}
      />

      {/* Domain & Record Selector Bar */}
      <DomainSelector
        collections={dynamicTabs}
        allDomains={liveDomainsStats}
        activeCollection={currentCollection}
        selectedCollectionId={selectedCollectionId}
        onSelectCollection={(id) => {
          setSelectedCollectionId(id);
          setSelectedDocIndex(0);
          setIsLoadingDomain(true);
        }}
        selectedDocIndex={selectedDocIndex}
        onSelectDocIndex={setSelectedDocIndex}
      />

      {/* Central Parity Status Bar */}
      <ParityBar
        collection={currentCollection}
      />

      {/* Database Connection Notice Banner */}
      {liveStatus && (!liveStatus.postgres.online || !liveStatus.raven.online) && (
        <div className="db-alert-banner">
          <div className="db-alert-content">
            <span className="db-alert-icon">⚠️</span>
            <div className="db-alert-text">
              <strong>Database Connection Notice:</strong>{' '}
              {!liveStatus.postgres.online && !liveStatus.raven.online ? (
                <span>Neither PostgreSQL nor RavenDB Cloud is connected.Please connect to  PostgreSQL and RavenDB server</span>
              ) : !liveStatus.postgres.online ? (
                <span>PostgreSQL is not reachable. Please connect to PostgreSQL server.</span>
              ) : (
                <span>RavenDB Cloud is not reachable. Please connect to RavenDB server.</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Main Workspace (Dual Panes: Live RavenDB Document vs Live PostgreSQL Row) */}
      <main className="panes-workspace">
        {isLoadingDomain && (
          <div className="syncing-indicator-bar">
            <span className="syncing-dot"></span>
            <span>Syncing live records from RavenDB Cloud & PostgreSQL...</span>
          </div>
        )}

        <div className="panes-container">
          {/* Left Pane: RavenDB Live Document */}
          <RavenPane
            collection={currentCollection}
            docIndex={selectedDocIndex}
          />

          {/* Right Pane: PostgreSQL Live Row */}
          <PostgresPane
            collection={currentCollection}
            docIndex={selectedDocIndex}
          />
        </div>
      </main>

      {/* AI Copilot Chat Drawer */}
      <AiChat
        collection={currentCollection}
        docIndex={selectedDocIndex}
      />

      {/* Live Parity Audit Modal */}
      <ParityAuditModal
        isOpen={isAuditModalOpen}
        onClose={() => setIsAuditModalOpen(false)}
        liveDomains={liveDomainsStats}
      />
    </div>
  );
}

export default App;
