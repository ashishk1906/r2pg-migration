import React from 'react';
import type { CollectionSummary } from '../types/migration';
import {
  CheckCheck,
  SplitSquareVertical,
  ChevronLeft,
  ChevronRight,
  Database,
  Table,
  Columns
} from 'lucide-react';
import { allAuditedDomainsList } from '../data/migrationData';

interface DomainSelectorProps {
  collections: CollectionSummary[];
  activeCollection?: CollectionSummary;
  selectedCollectionId: string;
  onSelectCollection: (id: string) => void;
  selectedDocIndex: number;
  onSelectDocIndex: (index: number) => void;
  viewMode: 'split' | 'transformation';
  onToggleViewMode: (mode: 'split' | 'transformation') => void;
}

export const DomainSelector: React.FC<DomainSelectorProps> = ({
  collections,
  activeCollection,
  selectedCollectionId,
  onSelectCollection,
  selectedDocIndex,
  onSelectDocIndex,
  viewMode,
  onToggleViewMode
}) => {
  const currentCollection = activeCollection || collections.find(c => c.id === selectedCollectionId) || collections[0];
  const docList = currentCollection.sampleDocuments || [];
  const totalRecords = docList.length;

  const handlePrev = () => {
    if (selectedDocIndex > 0) {
      onSelectDocIndex(selectedDocIndex - 1);
    }
  };

  const handleNext = () => {
    if (selectedDocIndex < totalRecords - 1) {
      onSelectDocIndex(selectedDocIndex + 1);
    }
  };

  return (
    <div className="domain-selector-bar">
      {/* Primary Domain Explorer Tabs */}
      <div className="domain-tabs-wrapper">
        <span className="selector-label">
          <SplitSquareVertical size={14} /> Domains:
        </span>
        <div className="domain-tabs">
          {collections.map(col => {
            const isSelected = col.id === selectedCollectionId;
            return (
              <button
                key={col.id}
                className={`domain-tab-btn ${isSelected ? 'active' : ''}`}
                onClick={() => {
                  onSelectCollection(col.id);
                  onSelectDocIndex(0);
                }}
              >
                <span className="tab-name">{col.name}</span>
                <span className="tab-count-chip">{col.documentCount}</span>
                {col.status === 'PASS' && (
                  <CheckCheck size={14} className="tab-status-icon text-success" />
                )}
              </button>
            );
          })}
        </div>

        {/* 42 Audited Domains Dropdown */}
        <div className="all-domains-dropdown-wrapper">
          <Database size={13} className="text-secondary" />
          <select
            className="all-domains-select"
            value={selectedCollectionId}
            onChange={e => {
              onSelectCollection(e.target.value);
              onSelectDocIndex(0);
            }}
          >
            <option value="" disabled>-- All 42 Audited Domains --</option>
            {allAuditedDomainsList.map((item, idx) => (
              <option key={idx} value={item.table}>
                {item.domain} ({item.count} docs • {item.fields} fields)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Record Navigation & View Mode Toggle */}
      <div className="selector-right-controls">
        {/* Record Navigator */}
        <div className="record-navigator">
          <button
            className="nav-arrow-btn"
            onClick={handlePrev}
            disabled={selectedDocIndex === 0}
            title="Previous Record"
          >
            <ChevronLeft size={16} />
          </button>

          <div className="record-dropdown-wrapper">
            <span className="record-count-text">
              Record <strong>{selectedDocIndex + 1}</strong> of <strong>{totalRecords}</strong>:
            </span>
            <select
              className="record-select-dropdown"
              value={selectedDocIndex}
              onChange={e => onSelectDocIndex(Number(e.target.value))}
            >
              {docList.map((doc, idx) => {
                const label =
                  doc.data?.Name ||
                  doc.data?.FullName ||
                  doc.data?.ApplicantName ||
                  doc.data?.name ||
                  doc.data?.first_name ||
                  doc.id;
                return (
                  <option key={idx} value={idx}>
                    #{idx + 1}: {doc.id} {label && label !== doc.id ? `(${label})` : ''}
                  </option>
                );
              })}
            </select>
          </div>

          <button
            className="nav-arrow-btn"
            onClick={handleNext}
            disabled={selectedDocIndex >= totalRecords - 1}
            title="Next Record"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* View Mode Switcher (Split vs Transformation Matrix) */}
        <div className="view-mode-toggle-group">
          <button
            className={`view-mode-btn ${viewMode === 'split' ? 'active' : ''}`}
            onClick={() => onToggleViewMode('split')}
            title="Side-by-side Dual Panes View"
          >
            <Columns size={13} />
            <span>Dual Panes</span>
          </button>
          <button
            className={`view-mode-btn ${viewMode === 'transformation' ? 'active' : ''}`}
            onClick={() => onToggleViewMode('transformation')}
            title="Full Field-by-Field Transformation Matrix"
          >
            <Table size={13} />
            <span>Transformation Matrix</span>
          </button>
        </div>
      </div>
    </div>
  );
};
