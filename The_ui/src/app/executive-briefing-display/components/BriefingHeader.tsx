'use client';

import React from 'react';
import { ExternalLink, FileText, Calendar, Users } from 'lucide-react';
import type { BriefingData } from './BriefingContent';

interface BriefingHeaderProps {
  briefing: BriefingData;
}

export default function BriefingHeader({ briefing }: BriefingHeaderProps) {
  return (
    <div className="retro-card-accent p-5 space-y-4">
      {/* Top meta row */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {briefing.categories.map(cat => (
            <span key={`header-cat-${cat}`} className="category-stamp">
              {cat}
            </span>
          ))}
          <span className="font-mono text-xs text-muted-foreground border border-border px-1.5 py-0.5 rounded-sm">
            {briefing.arxivId}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`https://arxiv.org/pdf/${briefing.arxivId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground border border-border px-2.5 py-1.5 rounded-sm transition-all duration-150 hover:border-primary"
          >
            <FileText size={11} />
            PDF
          </a>
          <a
            href={briefing.link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 retro-btn-ghost px-2.5 py-1.5 text-xs"
          >
            <ExternalLink size={11} />
            arXiv
          </a>
        </div>
      </div>

      {/* Title */}
      <div>
        <h1 className="font-serif text-xl lg:text-2xl font-semibold text-foreground leading-snug">
          {briefing.title}
        </h1>
        {briefing.selectionReason && (
          <p className="font-mono text-xs text-muted-foreground mt-1.5 flex items-start gap-1.5">
            <span className="text-primary shrink-0">⊕</span>
            <span>{briefing.selectionReason}</span>
          </p>
        )}
      </div>

      {/* Authors + date */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Users size={13} />
          <span className="font-sans text-sm">
            {briefing.authors.slice(0, 4).join(', ')}
            {briefing.authors.length > 4 && (
              <span className="text-muted-foreground"> + {briefing.authors.length - 4} more</span>
            )}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Calendar size={13} />
          <span className="font-mono text-sm">{briefing.publishDate}</span>
        </div>
      </div>

      {/* Divider */}
      <hr className="section-divider" />

      {/* Significance — prominently displayed */}
      <div>
        <p className="briefing-section-label mb-2">Why This Paper Matters</p>
        <p className="font-serif text-sm text-foreground leading-relaxed italic">
          {briefing.significance}
        </p>
      </div>
    </div>
  );
}