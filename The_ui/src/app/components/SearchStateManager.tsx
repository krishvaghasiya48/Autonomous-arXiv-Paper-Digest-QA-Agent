'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import SearchHero from './SearchHero';
import PipelineStatus from './PipelineStatus';
import CandidateList from './CandidateList';
import ClarificationPanel from './ClarificationPanel';

export type PipelineState =
  | 'idle' | 'running' | 'candidates' | 'clarification' | 'complete' | 'error';

export interface NodeTraceEntry {
  node: string;
  label: string;
  status: 'done' | 'active' | 'pending' | 'error';
  durationMs?: number;
}

export interface CandidatePaper {
  id: string;
  title: string;
  authors: string[];
  abstract: string;
  pdfUrl: string;
  categories: string[];
  published: string;
  selected?: boolean;
  selectionReason?: string;
}

const ALL_NODES: NodeTraceEntry[] = [
  { node: 'query_understanding', label: 'Query Understanding', status: 'pending' },
  { node: 'arxiv_retrieval',     label: 'arXiv Retrieval',    status: 'pending' },
  { node: 'selection',           label: 'Paper Selection',    status: 'pending' },
  { node: 'fetch_parse',         label: 'Fetch & Parse PDF',  status: 'pending' },
  { node: 'chunk_embed',         label: 'Chunk & Embed',      status: 'pending' },
  { node: 'summarize',           label: 'Generate Briefing',  status: 'pending' },
];

const canonicalNode = (name: string): string => {
  if (name === 'arxiv_retrieval_topic' || name === 'arxiv_retrieval_id') {
    return 'arxiv_retrieval';
  }
  return name;
};

export default function SearchStateManager() {
  const router = useRouter();

  const [pipelineState, setPipelineState] = useState<PipelineState>('idle');
  const [nodeTrace, setNodeTrace] = useState<NodeTraceEntry[]>(ALL_NODES);
  const [candidates, setCandidates] = useState<CandidatePaper[]>([]);
  const [query, setQuery] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [parseMethod, setParseMethod] = useState<string>('');
  const [totalFound, setTotalFound] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [currentArxivId, setCurrentArxivId] = useState<string | null>(null);
  const [clarificationSuggestions, setClarificationSuggestions] = useState<string[]>([]);

  const handleSearch = useCallback(async (inputQuery: string) => {
    console.log(`[UI REQUEST] query="${inputQuery}"`);
    setQuery(inputQuery);
    setPipelineState('running');
    setNodeTrace(ALL_NODES.map(n => ({ ...n, status: 'pending' })));
    setCandidates([]);
    setErrorMessage('');
    setCurrentArxivId(null);
    setClarificationSuggestions([]);

    const fakeJobId = `job-${Date.now()}`;
    setJobId(fakeJobId);

    let response: Response;
    try {
      response = await fetch('/api/digest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: inputQuery }),
      });
    } catch (err) {
      setPipelineState('error');
      setErrorMessage(err instanceof Error ? err.message : 'Network error');
      return;
    }

    if (!response.ok || !response.body) {
      setPipelineState('error');
      setErrorMessage(`Server error: ${response.status}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event: Record<string, unknown>;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          console.log('[FRONTEND EVENT RECEIVED]', event.type, event);

          switch (event.type) {
            case 'node_start': {
              const rawName = (event.node as string) || '';
              const nodeName = canonicalNode(rawName);
              console.log(`[SEARCH STATE] node_start: raw="${rawName}", canonical="${nodeName}"`);
              setNodeTrace(prev =>
                prev.map(n =>
                  n.node === nodeName ? { ...n, status: 'active' } : n
                )
              );
              break;
            }
            case 'node_done': {
              const rawName = (event.node as string) || '';
              const nodeName = canonicalNode(rawName);
              const durationMs = event.duration_ms as number | undefined;
              console.log(`[SEARCH STATE] node_done: raw="${rawName}", canonical="${nodeName}", durationMs=${durationMs}`);
              setNodeTrace(prev =>
                prev.map(n =>
                  n.node === nodeName
                    ? { ...n, status: 'done', durationMs }
                    : n
                )
              );
              break;
            }
            case 'candidates': {
              const papers = ((event.candidates || event.papers) ?? []) as CandidatePaper[];
              const total = (event.total_found ?? papers.length) as number;
              console.log(`[SEARCH STATE] candidates: count=${papers.length}, totalFound=${total}`);
              setCandidates(papers);
              setTotalFound(total);
              // Infer parseMethod from the selected paper if possible
              const selected = papers.find(p => p.selected);
              if (selected) setParseMethod('pymupdf');
              setPipelineState('candidates');
              break;
            }
            case 'complete': {
              const arxivId = event.arxiv_id as string;
              console.log(`[SEARCH STATE] complete: arxivId="${arxivId}"`);
              setCurrentArxivId(arxivId);
              // Route changes unmount this component. Keep the completed paper ID
              // so the global navigation can continue the same session.
              localStorage.setItem('arxiv-digest:last-arxiv-id', arxivId);
              // Mark all active/pending nodes as done
              setNodeTrace(prev =>
                prev.map(n =>
                  n.status === 'active' || n.status === 'pending'
                    ? { ...n, status: 'done' }
                    : n
                )
              );
              setPipelineState('complete');
              router.push(`/executive-briefing-display?id=${arxivId}`);
              break;
            }
            case 'clarification': {
              const suggestions = (event.suggestions ?? []) as string[];
              console.log(`[SEARCH STATE] clarification: suggestions count=${suggestions.length}`);
              setClarificationSuggestions(suggestions);
              setPipelineState('clarification');
              break;
            }
            case 'error': {
              const msg = event.message as string;
              console.log(`[SEARCH STATE] error: "${msg}"`);
              setErrorMessage(msg);
              setPipelineState('error');
              break;
            }
          }
        }
      }
    } catch (streamErr) {
      setPipelineState('error');
      setErrorMessage(streamErr instanceof Error ? streamErr.message : 'Stream error');
    }
  }, [router]);

  const handleClarificationSelect = (suggestion: string) => {
    handleSearch(suggestion);
  };

  const handleCandidateSelect = (paperId: string) => {
    setCandidates(prev =>
      prev.map(p => ({
        ...p,
        selected: p.id === paperId,
        selectionReason: p.id === paperId ? 'Manually selected by user.' : undefined,
      }))
    );
  };

  return (
    <div className="space-y-8">
      {/* Search hero — always visible */}
      <SearchHero
        onSearch={handleSearch}
        isRunning={pipelineState === 'running'}
      />

      {/* Pipeline status — visible when running or after */}
      {(pipelineState === 'running' || pipelineState === 'candidates' || pipelineState === 'complete') && (
        <PipelineStatus
          nodeTrace={nodeTrace}
          pipelineState={pipelineState}
          parseMethod={parseMethod}
          jobId={jobId}
          query={query}
          totalFound={totalFound}
        />
      )}

      {/* Error state */}
      {pipelineState === 'error' && (
        <div className="retro-card p-5 border-warning">
          <p className="font-mono text-xs text-warning tracking-widest uppercase mb-1">Pipeline Error</p>
          <p className="font-sans text-sm text-foreground">{errorMessage || 'An unknown error occurred.'}</p>
        </div>
      )}

      {/* Clarification panel — zero results */}
      {pipelineState === 'clarification' && (
        <ClarificationPanel
          suggestions={clarificationSuggestions}
          onSelect={handleClarificationSelect}
          query={query}
        />
      )}

      {/* Candidate papers */}
      {pipelineState === 'candidates' && candidates.length > 0 && (
        <CandidateList
          candidates={candidates}
          totalFound={totalFound}
          onSelectCandidate={handleCandidateSelect}
          arxivId={currentArxivId ?? undefined}
        />
      )}
    </div>
  );
}
