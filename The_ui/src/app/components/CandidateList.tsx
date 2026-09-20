'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, ExternalLink, Star, Users, Calendar } from 'lucide-react';
import type { CandidatePaper } from './SearchStateManager';

interface CandidateListProps {
  candidates: CandidatePaper[];
  totalFound: number;
  onSelectCandidate: (paperId: string) => void;
  /** arXiv ID of the paper that completed the digest pipeline, used for briefing links. */
  arxivId?: string;
}

export default function CandidateList({ candidates, totalFound, onSelectCandidate, arxivId }: CandidateListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(candidates.find(c => c.selected)?.id ?? null);

  return (
    <div className="space-y-4 slide-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted-foreground tracking-widest uppercase">
            Candidate Papers
          </span>
          <span className="font-mono text-xs border border-border px-1.5 py-0.5 rounded-sm text-muted-foreground">
            {candidates.length} shown
          </span>
          {totalFound > candidates.length && (
            <span className="font-mono text-xs text-muted-foreground">
              of {totalFound} found — ranked by relevance
            </span>
          )}
        </div>
        <Link
          href={arxivId ? `/executive-briefing-display?id=${arxivId}` : '/executive-briefing-display'}
          className="retro-btn flex items-center gap-1.5 px-3 py-1.5 text-xs"
        >
          View Briefing →
        </Link>
      </div>

      {/* Paper cards */}
      <div className="space-y-3">
        {candidates.map((paper, idx) => {
          const isExpanded = expandedId === paper.id;
          const arxivId = paper.pdfUrl.split('/').pop() || paper.id;

          return (
            <div
              key={paper.id}
              className={`retro-card transition-all duration-200 ${
                paper.selected
                  ? 'border-primary shadow-[2px_2px_0px_var(--primary)]'
                  : 'hover:border-muted-foreground'
              }`}
            >
              {/* Card header */}
              <div
                className="p-4 cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : paper.id)}
              >
                <div className="flex items-start gap-3">
                  {/* Rank badge */}
                  <div className={`shrink-0 w-6 h-6 rounded-sm flex items-center justify-center font-mono text-xs font-bold ${
                    paper.selected
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  }`}>
                    {idx + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    {/* Title row */}
                    <div className="flex items-start gap-2 flex-wrap">
                      <h3 className="font-serif text-sm font-semibold text-foreground leading-snug flex-1 min-w-0">
                        {paper.title}
                      </h3>
                      {paper.selected && (
                        <span className="flex items-center gap-1 font-mono text-xs text-primary border border-primary px-1.5 py-0.5 rounded-sm shrink-0">
                          <Star size={10} fill="currentColor" />
                          AUTO-SELECTED
                        </span>
                      )}
                    </div>

                    {/* Meta row */}
                    <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <Users size={11} />
                        <span className="font-sans text-xs truncate max-w-[200px]">
                          {paper.authors.slice(0, 3).join(', ')}{paper.authors.length > 3 ? ' +' + (paper.authors.length - 3) : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <Calendar size={11} />
                        <span className="font-mono text-xs">{paper.published}</span>
                      </div>
                      <a
                        href={`https://arxiv.org/abs/${arxivId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="flex items-center gap-1 font-mono text-xs text-primary hover:underline"
                      >
                        {arxivId.replace('v', ' v')}
                        <ExternalLink size={10} />
                      </a>
                    </div>

                    {/* Category stamps */}
                    <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                      {paper.categories.map(cat => (
                        <span
                          key={`cat-${paper.id}-${cat}`}
                          className={`category-stamp ${cat.startsWith('cs') ? '' : 'category-stamp-secondary'}`}
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Expand toggle */}
                  <button
                    className="shrink-0 text-muted-foreground hover:text-foreground transition-colors p-1"
                    aria-label={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                </div>
              </div>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-border pt-3 space-y-3 fade-in">
                  {/* Selection reason */}
                  {paper.selectionReason && (
                    <div className="flex items-start gap-2 bg-muted border border-border p-2.5 rounded-sm">
                      <span className="font-mono text-xs text-primary shrink-0 mt-0.5">⊕</span>
                      <div>
                        <p className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-0.5">Selection Reason</p>
                        <p className="font-sans text-xs text-foreground leading-relaxed">{paper.selectionReason}</p>
                      </div>
                    </div>
                  )}

                  {/* Abstract */}
                  <div>
                    <p className="briefing-section-label mb-1.5">Abstract</p>
                    <p className="font-sans text-sm text-muted-foreground leading-relaxed">
                      {paper.abstract}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={() => {
                        onSelectCandidate(paper.id);
                        /* Backend: POST /api/digest with selected paper override */
                      }}
                      className={`retro-btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs ${
                        paper.selected ? 'opacity-50 cursor-not-allowed' : ''
                      }`}
                      disabled={paper.selected}
                    >
                      {paper.selected ? '✓ Selected' : 'Select This Paper'}
                    </button>
                    <a
                      href={paper.pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground border border-border px-3 py-1.5 rounded-sm hover:border-border transition-all duration-150"
                    >
                      <ExternalLink size={11} />
                      PDF
                    </a>
                    <Link
                      href={arxivId ? `/executive-briefing-display?id=${arxivId}` : '/executive-briefing-display'}
                      className="flex items-center gap-1.5 font-mono text-xs text-secondary hover:text-foreground border border-secondary px-3 py-1.5 rounded-sm transition-all duration-150 hover:bg-muted"
                    >
                      View Briefing →
                    </Link>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}