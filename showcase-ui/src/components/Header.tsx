import React from 'react';
import { Database, CheckCircle2, Flame, Layers, Sparkles, RefreshCw, Radio } from 'lucide-react';
import confetti from 'canvas-confetti';
import type { MigrationParityStats } from '../types/migration';

interface HeaderProps {
  stats: MigrationParityStats;
  onRunAudit: () => void;
  onOpenAuditModal: () => void;
  isAuditing: boolean;
  liveStatus?: {
    postgres: { online: boolean; latencyMs?: number };
    raven: { online: boolean; latencyMs?: number };
    api: { online: boolean };
  } | null;
}

export const Header: React.FC<HeaderProps> = ({
  stats,
  onRunAudit,
  onOpenAuditModal,
  isAuditing,
  liveStatus
}) => {
  const triggerConfetti = () => {
    confetti({
      particleCount: 80,
      spread: 70,
      origin: { y: 0.2 },
      colors: ['#00d2d3', '#54a0ff', '#5f27cd', '#ff9f43', '#10ac84']
    });
    onRunAudit();
  };

  const isPgOnline = liveStatus ? liveStatus.postgres.online : false;
  const isRavenOnline = liveStatus ? liveStatus.raven.online : false;
  const isApiOnline = liveStatus ? liveStatus.api.online : false;

  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="logo-icon-wrapper">
          <Layers className="logo-icon" size={24} />
        </div>
        <div className="brand-text">
          <div className="brand-title">
            <span className="brand-highlight">CT-RPG</span> Migration Studio
            <span className="live-indicator-tag">
              <Radio size={12} className="pulse-icon" /> LIVE DB
            </span>
          </div>
          <div className="brand-subtitle">
            Real-time RavenDB (NoSQL) ➔ PostgreSQL Parity
          </div>
        </div>
      </div>

      <div className="header-center-badges">
        <div className={`status-badge source-badge ${isRavenOnline ? 'online' : 'offline'}`} title="Connected to RavenDB Cloud btl database">
          <Flame size={14} className="badge-icon-raven" />
          <span>RavenDB Cloud {liveStatus?.raven.latencyMs ? `(${liveStatus.raven.latencyMs}ms)` : ''}</span>
          <span className={`status-dot ${isRavenOnline ? 'green' : 'red'}`}></span>
        </div>
        <div className="arrow-separator">➔</div>
        <div className={`status-badge target-badge ${isPgOnline ? 'online' : 'offline'}`} title="Connected to PostgreSQL on localhost:5433">
          <Database size={14} className="badge-icon-pg" />
          <span>PostgreSQL {liveStatus?.postgres.latencyMs ? `(${liveStatus.postgres.latencyMs}ms)` : ''}</span>
          <span className={`status-dot ${isPgOnline ? 'green' : 'red'}`}></span>
        </div>
        <div className="arrow-separator">•</div>
        <div className={`status-badge api-badge ${isApiOnline ? 'online' : 'offline'}`}>
          <span>.NET 10 API</span>
          <span className={`status-dot ${isApiOnline ? 'green' : 'gray'}`}></span>
        </div>
      </div>

      <div className="header-actions">
        <button 
          className="metric-pill" 
          onClick={onOpenAuditModal}
          title="Click to view audited domains"
        >
          {isPgOnline && isRavenOnline && stats.collectionsAuditedCount > 0 ? (
            <>
              <CheckCircle2 size={16} className="text-success" />
              <span className="metric-text">
                <strong>{stats.collectionsAuditedCount} Domains Synced</strong> ({stats.totalDocumentsInRaven.toLocaleString()} Live Records)
              </span>
              <span className="badge-pass">100% {stats.overallStatus}</span>
            </>
          ) : (
            <>
              <Radio size={16} className="text-warning" />
              <span className="metric-text">
                <strong>0 Connected Domains</strong> (0 Live Records)
              </span>
              <span className="badge-pass" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                DISCONNECTED
              </span>
            </>
          )}
        </button>

        <button 
          className={`btn-primary ${isAuditing ? 'loading' : ''}`}
          onClick={triggerConfetti}
          disabled={isAuditing}
        >
          {isAuditing ? (
            <>
              <RefreshCw size={16} className="spin" />
              <span>Verifying...</span>
            </>
          ) : (
            <>
              <Sparkles size={16} />
              <span>Verify Parity</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
};
