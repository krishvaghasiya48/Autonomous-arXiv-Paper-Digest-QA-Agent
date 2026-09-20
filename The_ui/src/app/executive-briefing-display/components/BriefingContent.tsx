'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import BriefingHeader from './BriefingHeader';
import ParseDegradedBanner from './ParseDegradedBanner';
import BriefingBody from './BriefingBody';
import FollowUpChips from './FollowUpChips';
import BriefingViewToggle from './BriefingViewToggle';
import BriefingJsonViewer from './BriefingJsonViewer';
import { toast } from 'sonner';

export interface BriefingData {
  title: string;
  authors: string[];
  arxivId: string;
  publishDate: string;
  link: string;
  categories: string[];
  significance: string;
  problemStatement: string;
  approach: string[];
  keyResults: string[];
  limitations: string[];
  followUpQuestions: string[];
  parseDegraded: boolean;
  parseMethod: 'pymupdf' | 'pdfplumber' | 'abstract_only';
  nChunks: number;
  selectionReason?: string;
  truncationNote?: string;
}

export default function BriefingContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedArxivId = searchParams.get('id');
  const [arxivId, setArxivId] = useState<string | null>(requestedArxivId);

  const [briefing, setBriefing] = useState<BriefingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'rendered' | 'json'>('rendered');

  useEffect(() => {
    if (requestedArxivId) {
      localStorage.setItem('arxiv-digest:last-arxiv-id', requestedArxivId);
      setArxivId(requestedArxivId);
      return;
    }

    const savedArxivId = localStorage.getItem('arxiv-digest:last-arxiv-id');
    if (savedArxivId) {
      setArxivId(savedArxivId);
      router.replace(`/executive-briefing-display?id=${encodeURIComponent(savedArxivId)}`);
    } else {
      setArxivId(null);
    }
  }, [requestedArxivId, router]);

  useEffect(() => {
    if (!arxivId) {
      setError('No paper ID provided. Run a digest first.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    fetch(`/api/briefing/${arxivId}`)
      .then(r => {
        if (!r.ok) throw new Error(`Briefing not found (${r.status})`);
        return r.json();
      })
      .then((data: BriefingData) => {
        setBriefing(data);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [arxivId]);

  const handleDownload = (format: 'json' | 'md') => {
    if (!briefing) return;
    if (format === 'json') {
      const blob = new Blob([JSON.stringify(briefing, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${briefing.arxivId}_briefing.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
    toast.success(`Briefing downloaded as ${format.toUpperCase()}`);
  };

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="retro-card p-8 text-center space-y-3">
        <p className="font-mono text-xs text-primary tracking-widest uppercase animate-pulse">
          Loading Briefing…
        </p>
        {arxivId && (
          <p className="font-mono text-xs text-muted-foreground">{arxivId}</p>
        )}
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error || !briefing) {
    return (
      <div className="retro-card p-8 text-center space-y-3 border-warning">
        <p className="font-mono text-xs text-warning tracking-widest uppercase">
          Briefing Unavailable
        </p>
        <p className="font-sans text-sm text-foreground">{error ?? 'No briefing data.'}</p>
        <p className="font-mono text-xs text-muted-foreground">
          Run a digest from the home page first.
        </p>
      </div>
    );
  }

  // ── Loaded state ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Parse degraded warning */}
      {briefing.parseDegraded && <ParseDegradedBanner parseMethod={briefing.parseMethod} />}

      {/* Briefing header card */}
      <BriefingHeader briefing={briefing} />

      {/* View toggle + download */}
      <BriefingViewToggle
        viewMode={viewMode}
        onToggle={setViewMode}
        onDownload={handleDownload}
        nChunks={briefing.nChunks}
        parseMethod={briefing.parseMethod}
      />

      {/* Main content */}
      {viewMode === 'rendered' ? (
        <BriefingBody briefing={briefing} />
      ) : (
        <BriefingJsonViewer briefing={briefing} />
      )}

      {/* Follow-up questions */}
      <FollowUpChips questions={briefing.followUpQuestions} arxivId={briefing.arxivId} />
    </div>
  );
}
