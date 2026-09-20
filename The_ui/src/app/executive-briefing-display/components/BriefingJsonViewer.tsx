'use client';

import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import type { BriefingData } from './BriefingContent';

interface BriefingJsonViewProps {
  briefing: BriefingData;
}

export default function BriefingJsonView({ briefing }: BriefingJsonViewProps) {
  const [copied, setCopied] = useState(false);
  const jsonStr = JSON.stringify(briefing, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="retro-card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted">
        <span className="font-mono text-xs text-muted-foreground">briefing.json</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors duration-150"
        >
          {copied ? <Check size={11} className="text-secondary" /> : <Copy size={11} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-xs font-mono text-foreground leading-relaxed" style={{ maxHeight: '600px', overflowY: 'auto' }}>
        <code>{jsonStr}</code>
      </pre>
    </div>
  );
}