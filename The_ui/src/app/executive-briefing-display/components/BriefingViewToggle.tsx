'use client';

import React from 'react';
import { Download, Code, FileText } from 'lucide-react';

interface BriefingViewToggleProps {
  viewMode: 'rendered' | 'json';
  onToggle: (mode: 'rendered' | 'json') => void;
  onDownload: (format: 'json' | 'md') => void;
  nChunks: number;
  parseMethod: string;
}

export default function BriefingViewToggle({
  viewMode,
  onToggle,
  onDownload,
  nChunks,
  parseMethod,
}: BriefingViewToggleProps) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      {/* Left: stats */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-muted-foreground border border-border px-1.5 py-0.5 rounded-sm">
          {nChunks} chunks embedded
        </span>
        <span className={`font-mono text-xs border px-1.5 py-0.5 rounded-sm ${
          parseMethod === 'pymupdf' ?'border-secondary text-secondary'
            : parseMethod === 'pdfplumber' ?'border-primary text-primary' :'border-warning text-warning'
        }`}>
          {parseMethod}
        </span>
      </div>

      {/* Right: toggle + download */}
      <div className="flex items-center gap-2">
        {/* View mode toggle */}
        <div className="flex border border-border rounded-sm overflow-hidden">
          <button
            onClick={() => onToggle('rendered')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 font-mono text-xs transition-colors duration-150 ${
              viewMode === 'rendered' ?'bg-primary text-primary-foreground' :'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <FileText size={11} />
            Rendered
          </button>
          <button
            onClick={() => onToggle('json')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 font-mono text-xs transition-colors duration-150 border-l border-border ${
              viewMode === 'json' ?'bg-primary text-primary-foreground' :'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Code size={11} />
            JSON
          </button>
        </div>

        {/* Download */}
        <div className="flex border border-border rounded-sm overflow-hidden">
          <button
            onClick={() => onDownload('json')}
            className="flex items-center gap-1 px-2.5 py-1.5 font-mono text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors duration-150"
          >
            <Download size={11} />
            JSON
          </button>
          <button
            onClick={() => onDownload('md')}
            className="flex items-center gap-1 px-2.5 py-1.5 font-mono text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors duration-150 border-l border-border"
          >
            <Download size={11} />
            MD
          </button>
        </div>
      </div>
    </div>
  );
}