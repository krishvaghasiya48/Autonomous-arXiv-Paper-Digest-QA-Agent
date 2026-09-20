'use client';

import React from 'react';
import { AlertCircle, Search } from 'lucide-react';

interface ClarificationPanelProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
  query: string;
}

export default function ClarificationPanel({ suggestions, onSelect, query }: ClarificationPanelProps) {
  return (
    <div className="retro-card border-warning shadow-[2px_2px_0px_var(--warning)] p-5 space-y-4 slide-up">
      <div className="flex items-start gap-3">
        <AlertCircle size={16} className="text-warning shrink-0 mt-0.5" />
        <div>
          <p className="font-mono text-sm font-semibold text-warning">No papers found for this query</p>
          <p className="font-sans text-xs text-muted-foreground mt-1">
            The arXiv API returned zero results for <span className="font-mono text-foreground">&quot;{query}&quot;</span>.
            Try one of these broader searches:
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {suggestions.map((suggestion, idx) => (
          <button
            key={`suggestion-${idx}`}
            onClick={() => onSelect(suggestion)}
            className="w-full text-left flex items-center gap-2.5 followup-chip"
          >
            <Search size={12} className="text-primary shrink-0" />
            <span className="font-mono text-xs">{suggestion}</span>
          </button>
        ))}
      </div>
    </div>
  );
}