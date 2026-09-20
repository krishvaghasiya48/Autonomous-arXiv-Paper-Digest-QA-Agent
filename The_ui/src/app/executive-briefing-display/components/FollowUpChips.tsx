'use client';

import React from 'react';
import Link from 'next/link';
import { MessageSquare, ArrowRight } from 'lucide-react';

interface FollowUpChipsProps {
  questions: string[];
  arxivId: string;
}

export default function FollowUpChips({ questions, arxivId }: FollowUpChipsProps) {
  return (
    <div className="retro-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-primary" />
          <span className="font-mono text-xs font-bold tracking-widest uppercase text-primary">
            Follow-up Questions
          </span>
          <span className="font-mono text-xs text-muted-foreground border border-border px-1 py-0.5 rounded-sm">
            {questions.length}
          </span>
        </div>
        <Link
          href={`/qa-chat-interface?id=${arxivId}`}
          className="flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Open QA Chat <ArrowRight size={11} className="ml-0.5" />
        </Link>
      </div>

      <div className="space-y-2">
        {questions.map((q, idx) => (
          <Link
            key={`followup-${idx}`}
            href={`/qa-chat-interface?q=${encodeURIComponent(q)}&id=${arxivId}`}
            className="followup-chip flex items-start gap-2.5 w-full"
          >
            <span className="font-mono text-xs text-primary shrink-0 tabular-nums mt-0.5">
              Q{idx + 1}.
            </span>
            <span className="text-sm leading-snug">{q}</span>
          </Link>
        ))}
      </div>

      <div className="border-t border-border pt-3">
        <p className="font-mono text-xs text-muted-foreground">
          Click any question to pre-populate the QA chat. Answers will be grounded with chunk citations.
        </p>
      </div>
    </div>
  );
}
