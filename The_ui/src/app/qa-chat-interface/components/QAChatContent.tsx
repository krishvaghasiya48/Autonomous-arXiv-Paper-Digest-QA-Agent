'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import QASessionHeader from './QASessionHeader';
import QAThread from './QAThread';
import QAInputBar from './QAInputBar';
import { toast } from 'sonner';

export interface ChunkSource {
  id: string;
  label: string;
  section: string;
  page: number;
  text: string;
}

export interface QATurn {
  id: string;
  question: string;
  answer: string;
  citations: string[];
  chunks: ChunkSource[];
  isRefusal: boolean;
  retrievalMethod: 'hybrid' | 'dense' | 'bm25';
  timestamp: string;
  isLoading?: boolean;
}

interface SessionInfo {
  arxivId: string;
  title: string;
  nChunks: number;
  parseMethod: string;
}

export default function QAChatContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // arxivId comes from ?id= param (set by briefing page links and follow-up chips)
  const requestedArxivId = searchParams.get('id') ?? searchParams.get('arxivId') ?? '';
  const [arxivId, setArxivId] = useState(requestedArxivId);
  const prefilledQuestion = searchParams.get('q') ?? '';

  const [turns, setTurns] = useState<QATurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [session, setSession] = useState<SessionInfo>({
    arxivId,
    title: arxivId ? `arXiv: ${arxivId}` : 'No paper loaded',
    nChunks: 0,
    parseMethod: 'pymupdf',
  });
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (requestedArxivId) {
      localStorage.setItem('arxiv-digest:last-arxiv-id', requestedArxivId);
      setArxivId(requestedArxivId);
      return;
    }

    const savedArxivId = localStorage.getItem('arxiv-digest:last-arxiv-id');
    if (savedArxivId) {
      setArxivId(savedArxivId);
      router.replace(`/qa-chat-interface?id=${encodeURIComponent(savedArxivId)}`);
    } else {
      setArxivId('');
    }
  }, [requestedArxivId, router]);

  // Hydrate session info from the briefing endpoint
  useEffect(() => {
    if (!arxivId) return;
    fetch(`/api/briefing/${arxivId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!data) return;
        setSession({
          arxivId,
          title: data.title ?? `arXiv: ${arxivId}`,
          nChunks: data.nChunks ?? 0,
          parseMethod: data.parseMethod ?? 'pymupdf',
        });
      })
      .catch(() => {/* silently ignore — session header falls back gracefully */});
  }, [arxivId]);

  // Auto-scroll to bottom when turns update
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [turns]);

  const handleSubmitQuestion = useCallback(
    async (question: string) => {
      if (!question.trim() || isLoading) return;

      const loadingTurn: QATurn = {
        id: `turn-loading-${Date.now()}`,
        question,
        answer: '',
        citations: [],
        chunks: [],
        isRefusal: false,
        retrievalMethod: 'hybrid',
        timestamp: new Date().toLocaleTimeString('en-GB', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
        isLoading: true,
      };

      setTurns(prev => [...prev, loadingTurn]);
      setIsLoading(true);

      if (!arxivId) {
        setTurns(prev =>
          prev.map(t =>
            t.isLoading
              ? {
                  ...t,
                  isLoading: false,
                  answer: 'No paper loaded. Open a briefing first.',
                  isRefusal: true,
                }
              : t
          )
        );
        setIsLoading(false);
        return;
      }

      try {
        const res = await fetch(`/api/qa/${arxivId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
        });

        if (!res.ok) {
          throw new Error(`Server error: ${res.status}`);
        }

        const data = await res.json();

        const answeredTurn: QATurn = {
          id: data.id ?? `turn-${Date.now()}`,
          question,
          answer: data.answer ?? '',
          citations: data.citations ?? [],
          chunks: data.chunks ?? [],
          isRefusal: data.isRefusal ?? false,
          retrievalMethod: data.retrievalMethod ?? 'hybrid',
          timestamp:
            data.timestamp ??
            new Date().toLocaleTimeString('en-GB', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
        };

        setTurns(prev => prev.map(t => (t.isLoading ? answeredTurn : t)));

        if (answeredTurn.isRefusal) {
          toast.warning('Question out of scope — paper does not cover this topic.');
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Request failed';
        setTurns(prev =>
          prev.map(t =>
            t.isLoading
              ? {
                  ...t,
                  isLoading: false,
                  answer: `Error: ${msg}`,
                  isRefusal: true,
                }
              : t
          )
        );
        toast.error(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [arxivId, isLoading]
  );

  const handleClearHistory = () => {
    setTurns([]);
    toast.success('Conversation history cleared.');
  };

  return (
    <div className="flex flex-col gap-4" style={{ height: 'calc(100vh - 120px)' }}>
      {/* Session header */}
      <QASessionHeader
        session={session}
        turnCount={turns.length}
        onClearHistory={handleClearHistory}
      />

      {/* Thread */}
      <div
        ref={threadRef}
        className="flex-1 overflow-y-auto space-y-4 pr-1"
        style={{ minHeight: 0 }}
      >
        {turns.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="retro-card p-8 max-w-md">
              <p className="font-mono text-2xl text-primary mb-3">⊞</p>
              <p className="font-serif text-base font-semibold text-foreground mb-2">
                Ask anything about this paper
              </p>
              <p className="font-sans text-sm text-muted-foreground leading-relaxed">
                Every answer is grounded in the paper&apos;s content and cites chunk IDs.
                If the paper doesn&apos;t cover your question, the agent will say so exactly.
              </p>
            </div>
          </div>
        ) : (
          <QAThread turns={turns} />
        )}
      </div>

      {/* Input bar */}
      <QAInputBar
        onSubmit={handleSubmitQuestion}
        isLoading={isLoading}
        prefilledQuestion={prefilledQuestion}
        arxivId={session.arxivId}
      />
    </div>
  );
}
