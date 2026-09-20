'use client';

import React from 'react';
import Link from 'next/link';
import { ExternalLink, Trash2, FileText } from 'lucide-react';

interface SessionInfo {
  arxivId: string;
  title: string;
  nChunks: number;
  parseMethod: string;
}

interface QASessionHeaderProps {
  session: SessionInfo;
  turnCount: number;
  onClearHistory: () => void;
}

export default function QASessionHeader({ session, turnCount, onClearHistory }: QASessionHeaderProps) {
  return (
    <div className="retro-card p-3 flex items-start sm:items-center justify-between gap-3 flex-wrap">
      <div className="flex items-start sm:items-center gap-3 flex-wrap min-w-0">
        <div className="shrink-0">
          <div className="w-8 h-8 bg-primary flex items-center justify-center rounded-sm">
            <FileText size={14} className="text-primary-foreground" />
          </div>
        </div>
        <div className="min-w-0">
          <p className="font-serif text-sm font-semibold text-foreground truncate max-w-md">
            {session.title}
          </p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="font-mono text-xs text-primary">{session.arxivId}</span>
            <span className="font-mono text-xs text-muted-foreground border border-border px-1 py-0.5 rounded-sm">
              {session.nChunks} chunks
            </span>
            <span className={`font-mono text-xs border px-1 py-0.5 rounded-sm ${
              session.parseMethod === 'pymupdf' ?'border-secondary text-secondary' :'border-primary text-primary'
            }`}>
              {session.parseMethod}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {turnCount} turn{turnCount !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Link
          href={`/executive-briefing-display?id=${session.arxivId}`}
          className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground border border-border px-2.5 py-1.5 rounded-sm transition-all duration-150 hover:border-primary"
        >
          <FileText size={11} />
          Briefing
        </Link>
        <a
          href={`https://arxiv.org/abs/${session.arxivId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground border border-border px-2.5 py-1.5 rounded-sm transition-all duration-150"
        >
          <ExternalLink size={11} />
          arXiv
        </a>
        <button
          onClick={onClearHistory}
          className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-warning border border-border hover:border-warning px-2.5 py-1.5 rounded-sm transition-all duration-150"
          aria-label="Clear conversation history"
        >
          <Trash2 size={11} />
          Clear
        </button>
      </div>
    </div>
  );
}