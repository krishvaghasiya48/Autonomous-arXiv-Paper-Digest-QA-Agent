'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Search, ArrowRight, Zap, Hash } from 'lucide-react';
import Icon from '@/components/ui/AppIcon';


interface SearchHeroProps {
  onSearch: (query: string) => void;
  isRunning: boolean;
}

const EXAMPLE_QUERIES = [
  { label: 'Topic', text: 'efficient attention mechanisms in large language models', icon: Search },
  { label: 'arXiv ID', text: '2407.08608', icon: Hash },
  { label: 'URL', text: 'https://arxiv.org/abs/2401.00001', icon: Zap },
];

export default function SearchHero({ onSearch, isRunning }: SearchHeroProps) {
  const [query, setQuery] = useState('');
  const [inputFocused, setInputFocused] = useState(false);
  const [detectedType, setDetectedType] = useState<'topic' | 'arxiv_id' | 'url' | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const arxivIdPattern = /^\d{4}\.\d{4,5}(v\d+)?$/;
    const urlPattern = /arxiv\.org/;
    if (!query.trim()) {
      setDetectedType(null);
    } else if (urlPattern.test(query)) {
      setDetectedType('url');
    } else if (arxivIdPattern.test(query.trim())) {
      setDetectedType('arxiv_id');
    } else {
      setDetectedType('topic');
    }
  }, [query]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isRunning) return;
    onSearch(query.trim());
  };

  const handleExampleClick = (text: string) => {
    setQuery(text);
    inputRef.current?.focus();
  };

  const detectedTypeLabel: Record<string, string> = {
    topic: '◉ Topic search detected',
    arxiv_id: '◉ arXiv ID detected — direct lookup',
    url: '◉ arXiv URL detected — direct lookup',
  };

  const detectedTypeColor: Record<string, string> = {
    topic: 'text-secondary',
    arxiv_id: 'text-primary',
    url: 'text-primary',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <div className="font-mono text-xs text-muted-foreground tracking-widest uppercase border border-border px-2 py-0.5 rounded-sm">
            8byte / arxiv-agent
          </div>
          <div className="h-px flex-1 bg-border" />
          <div className="font-mono text-xs text-muted-foreground">
            v0.8.0 — 2026-09-18
          </div>
        </div>
        <h1 className="font-serif text-3xl lg:text-4xl font-semibold text-foreground tracking-tight">
          Autonomous Paper Intelligence
        </h1>
        <p className="font-sans text-sm text-muted-foreground max-w-2xl leading-relaxed">
          Submit a research topic or paste an arXiv paper ID / URL. The agent will fetch, parse, and
          embed the paper — then generate a structured executive briefing with grounded QA.
        </p>
      </div>

      {/* Main input form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div
          className={`relative retro-card transition-all duration-200 ${
            inputFocused ? 'border-primary shadow-[2px_2px_0px_var(--primary)]' : ''
          }`}
        >
          {/* Input type indicator */}
          {detectedType && (
            <div className={`absolute top-2.5 right-3 font-mono text-xs ${detectedTypeColor[detectedType]} flex items-center gap-1`}>
              <span className="pulse-dot">●</span>
              <span className="hidden sm:inline">{detectedTypeLabel[detectedType]}</span>
            </div>
          )}

          <textarea
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Enter a research topic, arXiv ID (e.g. 2407.08608), or full arXiv URL..."
            disabled={isRunning}
            rows={3}
            className={`w-full bg-transparent px-4 pt-4 pb-3 pr-40 font-sans text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none ${
              isRunning ? 'opacity-60 cursor-not-allowed' : ''
            } ${inputFocused && !detectedType ? 'cursor-blink' : ''}`}
            style={{ minHeight: '88px' }}
          />

          <div className="flex items-center justify-between px-3 pb-3 border-t border-border mt-0 pt-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-muted-foreground">
                Press <kbd className="border border-border px-1 py-0.5 rounded-sm text-xs bg-muted">Enter</kbd> to search
              </span>
            </div>
            <button
              type="submit"
              disabled={!query.trim() || isRunning}
              className="retro-btn flex items-center gap-2 px-4 py-2 text-xs"
            >
              {isRunning ? (
                <>
                  <span className="flex gap-0.5">
                    <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                    <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                    <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                  </span>
                  <span>Processing</span>
                </>
              ) : (
                <>
                  <span>Run Agent</span>
                  <ArrowRight size={13} />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Input format guide */}
        <div className="flex flex-wrap gap-2">
          <span className="font-mono text-xs text-muted-foreground self-center">Try:</span>
          {EXAMPLE_QUERIES.map(ex => {
            const Icon = ex.icon;
            return (
              <button
                key={`example-${ex.label}`}
                type="button"
                onClick={() => handleExampleClick(ex.text)}
                disabled={isRunning}
                className="flex items-center gap-1.5 font-mono text-xs border border-border text-muted-foreground hover:border-primary hover:text-primary px-2.5 py-1 rounded-sm transition-all duration-150 bg-muted disabled:opacity-40"
              >
                <Icon size={11} />
                <span className="text-primary font-medium">{ex.label}:</span>
                <span className="max-w-[160px] truncate">{ex.text}</span>
              </button>
            );
          })}
        </div>
      </form>

      {/* Info row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { icon: '⊕', title: 'Custom RAG Pipeline', desc: 'BM25 + dense hybrid retrieval, section-aware chunking' },
          { icon: '⊞', title: 'Section-aware Parsing', desc: 'PyMuPDF → pdfplumber fallback, never silent failure' },
          { icon: '⊟', title: 'Grounded QA', desc: 'Every answer cites chunk IDs — no hallucinations' },
        ].map(item => (
          <div key={`info-${item.icon}`} className="retro-card p-3 flex items-start gap-2.5">
            <span className="font-mono text-primary text-base mt-0.5 shrink-0">{item.icon}</span>
            <div>
              <p className="font-mono text-xs font-semibold text-foreground">{item.title}</p>
              <p className="font-sans text-xs text-muted-foreground mt-0.5 leading-relaxed">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}