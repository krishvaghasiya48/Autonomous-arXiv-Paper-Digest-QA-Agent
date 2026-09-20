'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, AlertTriangle, CheckCircle, Target, Wrench, BarChart2 } from 'lucide-react';
import type { BriefingData } from './BriefingContent';

interface BriefingBodyProps {
  briefing: BriefingData;
}

interface SectionProps {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  accent?: 'default' | 'warning' | 'secondary';
}

function BriefingSection({ label, icon, children, defaultOpen = true, accent = 'default' }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  const accentClass: Record<string, string> = {
    default: 'text-primary border-primary',
    warning: 'text-warning border-warning',
    secondary: 'text-secondary border-secondary',
  };

  return (
    <div className="retro-card overflow-hidden">
      <button
        onClick={() => setOpen(prev => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted transition-colors duration-150"
      >
        <div className="flex items-center gap-2">
          <span className={accentClass[accent]}>{icon}</span>
          <span className={`font-mono text-xs font-bold tracking-widest uppercase ${accentClass[accent]}`}>
            {label}
          </span>
        </div>
        {open ? (
          <ChevronUp size={13} className="text-muted-foreground" />
        ) : (
          <ChevronDown size={13} className="text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-border pt-3 fade-in">
          {children}
        </div>
      )}
    </div>
  );
}

export default function BriefingBody({ briefing }: BriefingBodyProps) {
  return (
    <div className="space-y-3">
      {/* Problem Statement */}
      <BriefingSection
        label="Problem Statement"
        icon={<Target size={13} />}
        accent="default"
      >
        <p className="font-sans text-sm text-foreground leading-relaxed">
          {briefing.problemStatement}
        </p>
      </BriefingSection>

      {/* Approach */}
      <BriefingSection
        label="Approach & Method"
        icon={<Wrench size={13} />}
        accent="secondary"
      >
        <ul className="space-y-2">
          {briefing.approach.map((item, idx) => (
            <li key={`approach-${idx}`} className="flex items-start gap-2.5">
              <span className="font-mono text-xs text-secondary shrink-0 mt-0.5 tabular-nums">
                {String(idx + 1).padStart(2, '0')}.
              </span>
              <p className="font-sans text-sm text-foreground leading-relaxed">{item}</p>
            </li>
          ))}
        </ul>
      </BriefingSection>

      {/* Key Results */}
      <BriefingSection
        label="Key Results & Claims"
        icon={<BarChart2 size={13} />}
        accent="secondary"
      >
        <ul className="space-y-2">
          {briefing.keyResults.map((result, idx) => (
            <li key={`result-${idx}`} className="flex items-start gap-2.5">
              <CheckCircle size={13} className="text-secondary shrink-0 mt-0.5" />
              <p className="font-sans text-sm text-foreground leading-relaxed">{result}</p>
            </li>
          ))}
        </ul>
      </BriefingSection>

      {/* Limitations — NEVER hidden by default */}
      <BriefingSection
        label="Limitations"
        icon={<AlertTriangle size={13} />}
        accent="warning"
        defaultOpen={true}
      >
        <div className="space-y-2">
          {briefing.limitations.length === 0 ? (
            <p className="font-mono text-xs text-warning">
              No limitations were extracted. The agent will re-prompt the LLM to infer limitations from the experimental setup.
            </p>
          ) : (
            briefing.limitations.map((lim, idx) => (
              <div key={`lim-${idx}`} className="flex items-start gap-2.5">
                <span className="font-mono text-xs text-warning shrink-0 mt-0.5">⊘</span>
                <p className="font-sans text-sm text-foreground leading-relaxed">{lim}</p>
              </div>
            ))
          )}
        </div>
      </BriefingSection>

      {/* Truncation note */}
      {briefing.truncationNote && (
        <div className="flex items-start gap-2 bg-muted border border-border p-3 rounded-sm">
          <span className="font-mono text-xs text-muted-foreground shrink-0 mt-0.5">ℹ</span>
          <p className="font-mono text-xs text-muted-foreground">{briefing.truncationNote}</p>
        </div>
      )}
    </div>
  );
}