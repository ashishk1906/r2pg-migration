export type DomainStatus = 'PASS' | 'FAIL' | 'AUDITING' | 'PENDING';

export interface DocumentMetadata {
  id: string;
  clrType?: string;
  lastModified?: string;
  changeVector?: string;
}

export interface RavenDocument {
  id: string;
  metadata: DocumentMetadata;
  data: Record<string, any>;
  rqlQuery?: string;
}

export interface PostgresRow {
  id: string;
  data: Record<string, any>;
  jsonbColumns?: Record<string, any>;
  columnTypes?: Record<string, string>;
  sqlQuery?: string;
  viewName?: string;
}

export interface CollectionSummary {
  id: string;
  name: string;
  ravenCollection: string;
  postgresTable: string;
  documentCount: number;
  rowCount: number;
  matchedCount: number;
  missingInPg: number;
  extraInPg: number;
  fieldMismatches: number;
  status: DomainStatus;
  primaryKey: string;
  sampleDocuments: RavenDocument[];
  sampleRows: PostgresRow[];
  ddl: string;
  triggers?: string;
  indexes?: string[];
  viewDefinition?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  codeSnippet?: {
    language: 'sql' | 'rql' | 'json' | 'csharp';
    code: string;
    title?: string;
  };
  actions?: Array<{
    label: string;
    actionKey: string;
  }>;
}

export interface MigrationParityStats {
  timestampUtc: string;
  collectionsAuditedCount: number;
  totalDocumentsInRaven: number;
  totalRowsInPostgres: number;
  totalMatchedIds: number;
  overallStatus: DomainStatus;
}
