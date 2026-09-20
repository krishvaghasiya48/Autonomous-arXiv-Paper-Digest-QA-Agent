'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, BookOpen } from 'lucide-react';
import Link from 'next/link';

interface QAInputBarProps {
  onSubmit: (question: string) => void;
  isLoading: boolean;
  prefilledQuestion: string;
  arxivId: string;
}

export default function QAInputBar({ onSubmit, isLoading, prefilledQuestion, arxivId }: QAInputBarProps) {
  const [question, setQuestion] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (prefilledQuestion) {
      setQuestion(prefilledQuestion);
      textareaRef.current?.focus();
    }
  }, [prefilledQuestion]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;
    onSubmit(question.trim());
    setQuestion('');
  };

  const QUICK_QUESTIONS = [
    'What dataset did they use for evaluation?',
    'What are the main limitations?',
    'How does the FP8 path handle numerical errors?',
  ];

  return (
    <div className="space-y-2">
      {/* Quick questions */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        <span className="font-mono text-xs text-muted-foreground shrink-0">Quick:</span>
        {QUICK_QUESTIONS.map((q, idx) => (
          <button
            key={`quick-${idx}`}
            onClick={() => {
              setQuestion(q);
              textareaRef.current?.focus();
            }}
            disabled={isLoading}
            className="followup-chip whitespace-nowrap shrink-0 text-xs disabled:opacity-40"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Main input */}
      <form onSubmit={handleSubmit}>
        <div className={`retro-card flex items-end gap-2 p-2 transition-all duration-200 ${
          question ? 'border-primary shadow-[2px_2px_0px_var(--primary)]' : ''
        }`}>
          <textarea
            ref={textareaRef}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder="Ask a grounded question about this paper..."
            disabled={isLoading}
            rows={2}
            className="flex-1 bg-transparent px-2 py-1.5 font-sans text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none disabled:opacity-50"
            style={{ minHeight: '52px', maxHeight: '120px' }}
          />

          <div className="flex flex-col items-end gap-1 shrink-0">
            <button
              type="submit"
              disabled={!question.trim() || isLoading}
              className="retro-btn flex items-center gap-1.5 px-3 py-2 text-xs"
              aria-label="Send question"
            >
              {isLoading ? (
                <span className="flex gap-0.5">
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                  <span className="typing-dot w-1 h-1 rounded-full bg-primary-foreground inline-block" />
                </span>
              ) : (
                <Send size={13} />
              )}
            </button>
            <span className="font-mono text-xs text-muted-foreground">
              ↵ send
            </span>
          </div>
        </div>
      </form>

      {/* Footer note */}
      <div className="flex items-center justify-between">
        <p className="font-mono text-xs text-muted-foreground">
          Answers grounded in <span className="text-primary font-medium">{arxivId}</span> — chunk citations required
        </p>
        <Link
          href="/"
          className="flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <BookOpen size={11} />
          New paper
        </Link>
      </div>
    </div>
  );
}