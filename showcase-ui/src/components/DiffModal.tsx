import React from 'react';
import type { CollectionSummary } from '../types/migration';
import { X, ArrowRightLeft, CheckCircle2, Sparkles } from 'lucide-react';

interface DiffModalProps {
  isOpen: boolean;
  onClose: () => void;
  collection: CollectionSummary;
}

export const DiffModal: React.FC<DiffModalProps> = ({ isOpen, onClose, collection }) => {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container diff-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <ArrowRightLeft size={22} className="text-primary" />
            <div>
              <h2 className="modal-title">Schema Transformation Matrix: {collection.name}</h2>
              <p className="modal-subtitle">
                <code>{collection.ravenCollection}</code> (NoSQL Document) ➔ <code>{collection.postgresTable}</code> (PostgreSQL Table)
              </p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-table-scroll">
          <table className="audit-data-table diff-table">
            <thead>
              <tr>
                <th>RavenDB Field (PascalCase)</th>
                <th>PostgreSQL Column (snake_case)</th>
                <th>Source Type</th>
                <th>Target Type</th>
                <th>Transformation Rule</th>
                <th>Parity Verification</th>
              </tr>
            </thead>
            <tbody>
              {collection.fieldMappings.map((m, i) => (
                <tr key={i}>
                  <td className="font-mono text-warning">{m.ravenField}</td>
                  <td className="font-mono text-info">{m.postgresColumn}</td>
                  <td><code>{m.sourceType}</code></td>
                  <td><code>{m.targetType}</code></td>
                  <td>
                    <span className="rule-badge">{m.transformRule}</span>
                    {m.notes && <div className="rule-note">{m.notes}</div>}
                  </td>
                  <td>
                    <span className="badge-pass">
                      <CheckCircle2 size={13} /> {m.isMatched ? 'MATCH (100%)' : 'MISMATCH'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="modal-footer">
          <span className="footer-note">
            <Sparkles size={14} className="text-warning" /> Canonical mapping rules enforced by Python ETL
          </span>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
