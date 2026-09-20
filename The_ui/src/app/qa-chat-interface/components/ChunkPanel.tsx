'use client';

import React, { useState } from 'react';
import type { ChunkSource } from './QAChatContent';

interface ChunkPanelProps {
  chunks: ChunkSource[];
}

export default function ChunkPanel({ chunks }: ChunkPanelProps) {
  const [expandedChunk, setExpandedChunk] = useState<string | null>(chunks[0]?.id ?? null);

  return (
    <div className="terminal-panel p-3 space-y-2 fade-in">
      <p className="font-mono text-xs text-muted-foreground tracking-widest uppercase mb-2">
        Retrieved Source Chunks
      </p>
      {chunks.map(chunk => {
        const isExpanded = expandedChunk === chunk.id;
        return (
          <div
            key={`chunk-${chunk.id}`}
            className="border border-border rounded-sm overflow-hidden"
          >
            <button
              onClick={() => setExpandedChunk(isExpanded ? null : chunk.id)}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-muted transition-colors duration-150"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="chunk-label">{chunk.label}</span>
              </div>
              <span className="font-mono text-xs text-muted-foreground ml-2 shrink-0">
                {isExpanded ? '▲' : '▼'}
              </span>
            </button>

            {isExpanded && (
              <div className="px-3 pb-3 border-t border-border pt-2 fade-in">
                <p className="font-mono text-xs leading-relaxed" style={{ color: 'var(--terminal-green)' }}>
                  {chunk.text}
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}