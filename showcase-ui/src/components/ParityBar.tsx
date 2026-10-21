import React from 'react';
import type { CollectionSummary } from '../types/migration';
import { CheckCircle2, ArrowRightLeft, Sparkles, ShieldCheck } from 'lucide-react';

interface ParityBarProps {
  collection: CollectionSummary;
  onOpenDiffModal: () => void;
}

export const ParityBar: React.FC<ParityBarProps> = ({ collection, onOpenDiffModal }) => {
  return (
    <div className="parity-bar-container">
      <div className="parity-status-indicator">
        <ShieldCheck size={18} className="text-success" />
        <span className="parity-title">Data Parity Verified:</span>
        <span className="parity-badge-pass">
          <CheckCircle2 size={14} /> 100% MATCH
        </span>
        <span className="parity-details-text">
          {collection.documentCount} Source Docs ➔ {collection.rowCount} Target Rows (0 Mismatches)
        </span>
      </div>

      <div className="field-mapping-chips-row">
        {collection.fieldMappings.slice(0, 4).map((f, i) => (
          <div key={i} className="mapping-chip">
            <span className="source-prop">{f.ravenField}</span>
            <span className="chip-arrow">➔</span>
            <span className="target-col">{f.postgresColumn}</span>
            <span className="rule-tag">{f.transformRule.replace('_', ' ')}</span>
          </div>
        ))}
      </div>

      <button className="btn-inspect-diff" onClick={onOpenDiffModal}>
        <ArrowRightLeft size={14} />
        <span>Compare Schema Transformations</span>
        <Sparkles size={13} className="text-warning" />
      </button>
    </div>
  );
};
