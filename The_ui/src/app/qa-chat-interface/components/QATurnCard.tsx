'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, AlertOctagon, Clock } from 'lucide-react';
import ChunkPanel from './ChunkPanel';
import type { QATurn } from './QAChatContent';

interface QATurnCardProps {
  turn: QATurn;
}

function parseCitations(text: string, citations: string[]) {
  if (!citations.length) return <span>{text}</span>;

  const parts = text.split(/(\[C\d+\])/g);
  return (
    <>
      {parts.map((part, idx) => {
        const match = part.match(/^\[C(\d+)\]$/);
        if (match) {
          return (
            <span key={`cit-${idx}-${part}`} className="citation-badge mx-0.5">
              {part}
            </span>
          );
        }
        return <span key={`text-${idx}`}>{part}</span>;
      })}
    </>
  );
}

export default function QATurnCard({ turn }: QATurnCardProps) {
  const [chunksOpen, setChunksOpen] = useState(false);

  if (turn.isLoading) {
    return (
      <div className="space-y-2 slide-up">
        {/* Question */}
        <div className="flex justify-end">
          <div className="retro-card bg-muted px-4 py-2.5 max-w-2xl">
            <p className="font-sans text-sm text-foreground">{turn.question}</p>
          </div>
        </div>
        {/* Loading answer */}
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 shrink-0 bg-primary rounded-sm flex items-center justify-center mt-0.5">
            <span className="font-mono text-xs text-primary-foreground font-bold">A</span>
          </div>
          <div className="retro-card px-4 py-3 flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">Retrieving</span>
            <span className="flex gap-1">
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
              <span className="typing-dot w-1.5 h-1.5 rounded-full bg-primary inline-block" />
            </span>
            <span className="font-mono text-xs text-muted-foreground">BM25 + dense hybrid</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2 slide-up">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className="retro-card border-primary shadow-[1px_1px_0px_var(--primary)] px-4 py-2.5 max-w-2xl">
          <div className="flex items-start gap-2">
            <div className="w-5 h-5 shrink-0 bg-muted rounded-sm flex items-center justify-center mt-0.5">
              <span className="font-mono text-xs text-muted-foreground font-bold">Q</span>
            </div>
            <p className="font-sans text-sm text-foreground leading-relaxed">{turn.question}</p>
          </div>
        </div>
      </div>

      {/* Answer */}
      <div className="flex items-start gap-3">
        <div className={`w-6 h-6 shrink-0 rounded-sm flex items-center justify-center mt-0.5 ${
          turn.isRefusal ? 'bg-refusal' : 'bg-primary'
        }`}>
          <span className="font-mono text-xs font-bold" style={{ color: turn.isRefusal ? 'var(--refusal)' : 'var(--primary-foreground)' }}>
            {turn.isRefusal ? '⊘' : 'A'}
          </span>
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          {/* Answer bubble */}
          {turn.isRefusal ? (
            <div className="refusal-response px-4 py-3 space-y-1.5">
              <div className="flex items-center gap-2">
                <AlertOctagon size={13} className="text-refusal shrink-0" />
                <span className="font-mono text-xs font-bold text-refusal tracking-wider uppercase">
                  Out of scope
                </span>
              </div>
              <p className="font-mono text-sm text-refusal">
                Not stated in this paper.
              </p>
              <p className="font-sans text-xs text-refusal opacity-70 mt-1">
                The retrieved chunks do not contain information relevant to this question.
                The paper&apos;s coverage is limited to FlashAttention-3 implementation on H100 GPUs.
              </p>
            </div>
          ) : (
            <div className="retro-card px-4 py-3">
              <p className="font-sans text-sm text-foreground leading-relaxed">
                {parseCitations(turn.answer, turn.citations)}
              </p>
            </div>
          )}

          {/* Metadata row */}
          <div className="flex items-center gap-3 px-1 flex-wrap">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Clock size={10} />
              <span className="font-mono text-xs">{turn.timestamp}</span>
            </div>
            <span className="font-mono text-xs border border-border px-1.5 py-0.5 rounded-sm text-muted-foreground">
              {turn.retrievalMethod}
            </span>
            {turn.citations.length > 0 && (
              <div className="flex items-center gap-1">
                {turn.citations.map(c => (
                  <span key={`meta-cit-${turn.id}-${c}`} className="citation-badge">
                    {c}
                  </span>
                ))}
              </div>
            )}

            {/* Expand chunks */}
            {turn.chunks.length > 0 && (
              <button
                onClick={() => setChunksOpen(prev => !prev)}
                className="flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors duration-150 ml-auto"
              >
                {chunksOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                {chunksOpen ? 'Hide' : 'Show'} {turn.chunks.length} source chunk{turn.chunks.length !== 1 ? 's' : ''}
              </button>
            )}
          </div>

          {/* Source chunks */}
          {chunksOpen && turn.chunks.length > 0 && (
            <ChunkPanel chunks={turn.chunks} />
          )}
        </div>
      </div>
    </div>
  );
}