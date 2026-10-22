import React from 'react';
import type { CollectionSummary } from '../types/migration';
import { CheckCircle2, ShieldCheck } from 'lucide-react';

interface ParityBarProps {
  collection: CollectionSummary;
}

export const ParityBar: React.FC<ParityBarProps> = ({ collection }) => {
  const isMatch = collection.documentCount > 0 && collection.rowCount > 0 && collection.documentCount === collection.rowCount;

  return (
    <div className="parity-bar-container">
      <div className="parity-status-indicator">
        {isMatch ? (
          <>
            <ShieldCheck size={18} className="text-success" />
            <span className="parity-title">Data Parity Verified:</span>
            <span className="parity-badge-pass">
              <CheckCircle2 size={14} /> 100% MATCH
            </span>
            <span className="parity-details-text">
              {collection.documentCount} Source Docs ➔ {collection.rowCount} Target Rows (0 Mismatches)
            </span>
          </>
        ) : (
          <>
            <ShieldCheck size={18} className="text-warning" />
            <span className="parity-title">Live Database Status:</span>
            <span className="parity-badge-pass" style={{ background: 'rgba(255, 165, 2, 0.15)', color: '#ffa502', borderColor: 'rgba(255, 165, 2, 0.3)' }}>
              AWAITING SYNC
            </span>
            <span className="parity-details-text">
              {collection.documentCount} RavenDB Docs ➔ {collection.rowCount} PostgreSQL Rows (Connect databases to view live records)
            </span>
          </>
        )}
      </div>
    </div>
  );
};
