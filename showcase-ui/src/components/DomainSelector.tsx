import React from 'react';
import type { CollectionSummary } from '../types/migration';
import {
  CheckCheck,
  SplitSquareVertical,
  ChevronLeft,
  ChevronRight,
  Database
} from 'lucide-react';

export interface LiveDomainRef {
  domain?: string;
  collection?: string;
  table?: string;
  ravenCount?: number | string;
  pgCount?: number | string;
}

interface DomainSelectorProps {
  collections: CollectionSummary[];
  allDomains?: LiveDomainRef[];
  activeCollection?: CollectionSummary;
  selectedCollectionId: string;
  onSelectCollection: (id: string) => void;
  selectedDocIndex: number;
  onSelectDocIndex: (index: number) => void;
}

export const DomainSelector: React.FC<DomainSelectorProps> = ({
  collections,
  allDomains = [],
  activeCollection,
  selectedCollectionId,
  onSelectCollection,
  selectedDocIndex,
  onSelectDocIndex
}) => {
  const currentCollection = activeCollection || collections.find(c => c.id === selectedCollectionId) || collections[0];
  const docList = currentCollection?.sampleDocuments || [];
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

  // Fast windowed options to prevent thousands of DOM nodes while supporting all records
  const visibleRecordOptions = React.useMemo(() => {
    if (totalRecords <= 120) {
      return docList.map((doc, idx) => {
        const name = doc.data?.Name || doc.data?.FullName || doc.data?.name || '';
        return {
          idx,
          label: `#${idx + 1}: ${doc.id} ${name ? `(${name})` : ''}`
        };
      });
    }

    const indexSet = new Set<number>();
    for (let i = 0; i < Math.min(5, totalRecords); i++) indexSet.add(i);
    const start = Math.max(0, selectedDocIndex - 35);
    const end = Math.min(totalRecords - 1, selectedDocIndex + 35);
    for (let i = start; i <= end; i++) indexSet.add(i);
    for (let i = Math.max(0, totalRecords - 5); i < totalRecords; i++) indexSet.add(i);

    return Array.from(indexSet)
      .sort((a, b) => a - b)
      .map(idx => {
        const doc = docList[idx];
        const name = doc?.data?.Name || doc?.data?.FullName || doc?.data?.name || '';
        return {
          idx,
          label: `#${idx + 1}: ${doc?.id || idx} ${name ? `(${name})` : ''}`
        };
      });
  }, [docList, totalRecords, selectedDocIndex]);

  const tabsContainerRef = React.useRef<HTMLDivElement>(null);

  const scrollTabs = (direction: 'left' | 'right') => {
    if (tabsContainerRef.current) {
      const scrollAmount = 300;
      tabsContainerRef.current.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth'
      });
    }
  };

  const handleTabsWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (tabsContainerRef.current && e.deltaY !== 0) {
      e.currentTarget.scrollLeft += e.deltaY * 1.5;
    }
  };

  // Automatically scroll selected tab into view
  React.useEffect(() => {
    if (!tabsContainerRef.current) return;
    const activeTab = tabsContainerRef.current.querySelector('.domain-tab-btn.active') as HTMLElement;
    if (activeTab) {
      activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [selectedCollectionId]);

  return (
    <div className="domain-selector-bar">
      <div className="domain-tabs-wrapper">
        <span className="selector-label">
          <SplitSquareVertical size={14} /> Domains:
        </span>

        {/* Expandable Dropdown: All 42 Tables & Domains */}
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
            <option value="" disabled>
              {allDomains && allDomains.length > 0
                ? `-- Live Discovered Tables (${allDomains.length}) --`
                : '-- Awaiting Live Database Tables --'}
            </option>
            {allDomains && allDomains.length > 0 ? (
              allDomains
                .filter(item => !item.collection?.startsWith('@'))
                .map((item, idx) => {
                  const targetVal = item.table || item.collection || '';
                  const displayName = item.domain || item.collection || item.table || 'Unknown';
                  const countBadge = typeof item.ravenCount === 'number' && item.ravenCount > 0 ? `(${item.ravenCount} docs)` : '';
                  return (
                    <option key={idx} value={targetVal}>
                      {displayName} {countBadge}
                    </option>
                  );
                })
            ) : (
              <option value="" disabled>No tables loaded. Connect PostgreSQL or RavenDB.</option>
            )}
          </select>
        </div>

        {/* Quick Domain Tabs with Left/Right Scroll Controls */}
        <div className="domain-tabs-scroll-container">
          <button
            type="button"
            className="tabs-scroll-arrow-btn"
            onClick={() => scrollTabs('left')}
            title="Scroll tables left"
            aria-label="Scroll tables left"
          >
            <ChevronLeft size={15} />
          </button>

          <div
            ref={tabsContainerRef}
            className="domain-tabs"
            onWheel={handleTabsWheel}
          >
            {collections && collections.length > 0 ? (
              collections.map(col => {
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
                    {col.documentCount > 0 && (
                      <span className="tab-count-chip">{col.documentCount}</span>
                    )}
                    {col.status === 'PASS' && col.documentCount > 0 && (
                      <CheckCheck size={14} className="tab-status-icon text-success" />
                    )}
                  </button>
                );
              })
            ) : (
              <span className="text-muted text-small" style={{ padding: '0.35rem 0.6rem', color: '#64748b' }}>
                No live collections loaded. Connect databases to inspect.
              </span>
            )}
          </div>

          <button
            type="button"
            className="tabs-scroll-arrow-btn"
            onClick={() => scrollTabs('right')}
            title="Scroll tables right"
            aria-label="Scroll tables right"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>

      {/* Record Navigation Controls */}
      <div className="selector-right-controls">
        <div className="record-navigator">
          <button
            className="nav-arrow-btn"
            onClick={handlePrev}
            disabled={totalRecords === 0 || selectedDocIndex === 0}
            title="Previous Record"
          >
            <ChevronLeft size={16} />
          </button>

          <div className="record-dropdown-wrapper">
            <span className="record-count-text">
              {totalRecords > 0 ? (
                <>
                  Record{' '}
                  <input
                    type="number"
                    className="record-jump-number-input"
                    min={1}
                    max={totalRecords}
                    value={selectedDocIndex + 1}
                    onChange={e => {
                      const v = parseInt(e.target.value, 10);
                      if (!isNaN(v) && v >= 1 && v <= totalRecords) {
                        onSelectDocIndex(v - 1);
                      }
                    }}
                    title="Direct jump: Type any record number"
                  />{' '}
                  of <strong>{totalRecords}</strong>:
                </>
              ) : (
                <span className="text-muted">0 Live Records</span>
              )}
            </span>
            <select
              className="record-select-dropdown"
              value={selectedDocIndex}
              onChange={e => onSelectDocIndex(Number(e.target.value))}
              disabled={totalRecords === 0}
            >
              {totalRecords === 0 ? (
                <option value={0}>No live records loaded</option>
              ) : (
                visibleRecordOptions.map(opt => (
                  <option key={opt.idx} value={opt.idx}>
                    {opt.label}
                  </option>
                ))
              )}
            </select>
          </div>

          <button
            className="nav-arrow-btn"
            onClick={handleNext}
            disabled={totalRecords === 0 || selectedDocIndex >= totalRecords - 1}
            title="Next Record"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};
