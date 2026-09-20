'use client';

import React, { useEffect, useRef } from 'react';
import { CheckCircle, Circle, AlertCircle, Loader } from 'lucide-react';
import type { NodeTraceEntry, PipelineState } from './SearchStateManager';

interface PipelineStatusProps {
  nodeTrace: NodeTraceEntry[];
  pipelineState: PipelineState;
  parseMethod: string;
  jobId: string | null;
  query: string;
  totalFound: number;
}

const NODE_DESCRIPTIONS: Record<string, string> = {
  query_understanding: 'Parsing intent — detecting arXiv ID vs. topic search',
  arxiv_retrieval: 'Querying arXiv Atom API with tenacity retry logic',
  selection: 'Ranking candidates by relevance + recency, selecting top paper',
  fetch_parse: 'Downloading PDF, extracting sections with PyMuPDF',
  chunk_embed: 'Section-aware chunking (~900 chars), embedding with all-MiniLM-L6-v2',
  summarize: 'Generating structured executive briefing via LLM',
};

export default function PipelineStatus({
  nodeTrace,
  pipelineState,
  parseMethod,
  jobId,
  query,
  totalFound,
}: PipelineStatusProps) {
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [nodeTrace]);

  const activeNode = nodeTrace.find(n => n.status === 'active');
  const doneCount = nodeTrace.filter(n => n.status === 'done').length;
  const totalNodes = nodeTrace.filter(n => n.node !== 'selection' || totalFound > 1).length;
  const progressPct = totalNodes > 0 ? Math.round((doneCount / totalNodes) * 100) : 0;

  return (
    <div className="space-y-3 slide-up">
      {/* Status header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">Pipeline Trace</span>
          {jobId && (
            <span className="font-mono text-xs text-muted-foreground border border-border px-1.5 py-0.5 rounded-sm">
              {jobId}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {parseMethod && (
            <span className={`font-mono text-xs border px-1.5 py-0.5 rounded-sm ${
              parseMethod === 'pymupdf' ?'border-secondary text-secondary'
                : parseMethod === 'pdfplumber' ?'text-primary border-primary' :'text-warning border-warning'
            }`}>
              {parseMethod}
            </span>
          )}
          <span className="font-mono text-xs text-muted-foreground">{doneCount}/{totalNodes} nodes</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary transition-all duration-500 ease-out"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Terminal output */}
      <div
        ref={terminalRef}
        className="terminal-panel p-4 overflow-y-auto"
        style={{ maxHeight: '240px', minHeight: '120px' }}
      >
        {/* Header line */}
        <div className="node-trace-line done mb-1">
          <span className="text-terminal-green">$</span>
          <span className="text-terminal-green opacity-70">arxiv-agent run</span>
          <span className="text-muted-foreground opacity-50 ml-2 truncate max-w-xs">
            &quot;{query}&quot;
          </span>
        </div>

        <div className="w-full h-px bg-border opacity-30 my-2" />

        {nodeTrace.map(entry => {
          const isRelevant = entry.status !== 'pending' || entry.node !== 'selection' || totalFound > 1;
          if (!isRelevant && entry.node === 'selection') return null;

          return (
            <div
              key={`trace-${entry.node}`}
              className={`node-trace-line ${entry.status}`}
            >
              {/* Status icon */}
              <span className="shrink-0 w-4">
                {entry.status === 'done' && <CheckCircle size={12} className="text-terminal-green" />}
                {entry.status === 'active' && <Loader size={12} className="text-primary animate-spin" />}
                {entry.status === 'pending' && <Circle size={12} className="opacity-30" />}
                {entry.status === 'error' && <AlertCircle size={12} className="text-warning" />}
              </span>

              {/* Arrow */}
              <span className="opacity-60">→</span>

              {/* Node name */}
              <span className={`font-semibold ${
                entry.status === 'done' ? 'text-terminal-green' :
                entry.status === 'active'? 'text-primary' : 'opacity-40'
              }`}>
                {entry.node}
              </span>

              {/* Description */}
              <span className="hidden lg:inline text-muted-foreground opacity-60 text-xs truncate">
                — {NODE_DESCRIPTIONS[entry.node] || ''}
              </span>

              {/* Duration */}
              {entry.status === 'done' && entry.durationMs && (
                <span className="ml-auto text-muted-foreground opacity-50 tabular-nums shrink-0">
                  {entry.durationMs}ms
                </span>
              )}

              {/* Active indicator */}
              {entry.status === 'active' && (
                <span className="ml-auto shrink-0 flex gap-0.5">
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary inline-block" />
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary inline-block" />
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary inline-block" />
                </span>
              )}
            </div>
          );
        })}

        {/* Completion line */}
        {pipelineState === 'candidates' && (
          <div className="node-trace-line done mt-2">
            <CheckCircle size={12} className="text-terminal-green shrink-0" />
            <span className="text-terminal-green">→ Pipeline complete.</span>
            {totalFound > 0 && (
              <span className="text-muted-foreground opacity-70 ml-1">
                {totalFound} papers found. Showing candidates below.
              </span>
            )}
          </div>
        )}
      </div>

      {/* Active node description */}
      {activeNode && (
        <div className="flex items-center gap-2 font-mono text-xs text-primary">
          <Loader size={11} className="animate-spin shrink-0" />
          <span>{NODE_DESCRIPTIONS[activeNode.node] || activeNode.label}</span>
        </div>
      )}
    </div>
  );
}