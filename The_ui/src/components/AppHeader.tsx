'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import AppLogo from '@/components/ui/AppLogo';
import { useTheme } from '@/components/ThemeProvider';
import { Sun, Moon, BookOpen, MessageSquare, FileText, Menu, X, ChevronDown } from 'lucide-react';
import Icon from '@/components/ui/AppIcon';


interface Session {
  arxivId: string;
  title: string;
  nChunks: number;
}

interface ApiSession {
  arxiv_id: string;
  title: string;
  n_chunks: number;
}

export default function AppHeader() {
  const { theme, toggleTheme } = useTheme();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [activeArxivId, setActiveArxivId] = useState('');
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    setActiveArxivId(localStorage.getItem('arxiv-digest:last-arxiv-id') ?? '');

    fetch('/api/sessions')
      .then(response => (response.ok ? response.json() : []))
      .then((data: ApiSession[]) => setSessions(
        data
          .filter(session => session.arxiv_id)
          .map(session => ({
            arxivId: session.arxiv_id,
            title: session.title,
            nChunks: session.n_chunks,
          }))
      ))
      .catch(() => setSessions([]));
  }, [pathname]);

  const paperHref = (path: string) =>
    activeArxivId ? `${path}?id=${encodeURIComponent(activeArxivId)}` : path;

  const navLinks = [
    { href: '/', label: 'Search', icon: BookOpen },
    { href: paperHref('/executive-briefing-display'), label: 'Briefing', icon: FileText },
    { href: paperHref('/qa-chat-interface'), label: 'QA Chat', icon: MessageSquare },
  ];

  return (
    <header className="sticky top-0 z-50 w-full bg-card border-b border-border">
      <div className="max-w-screen-2xl mx-auto px-4 lg:px-8 xl:px-10 2xl:px-16 h-14 flex items-center justify-between gap-4">
        {/* Logo + title */}
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-sm bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <BookOpen size={16} />
          </div>
          <span className="font-serif font-semibold text-base tracking-tight text-foreground hidden sm:block">
            Arxiv<span className="text-primary">Digest</span>
          </span>
          <span className="font-mono text-xs text-muted-foreground hidden md:block border border-border px-1.5 py-0.5 rounded-sm">
            v0.8
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          {navLinks.map(link => {
            const Icon = link.icon;
            const isActive = link.href === '/' ? pathname === '/' : pathname === link.href;
            return (
              <Link
                key={`nav-${link.href}`}
                href={link.href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm font-mono text-xs font-medium tracking-wide transition-all duration-150 ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                <Icon size={13} />
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Right controls */}
        <div className="flex items-center gap-2">
          {/* Session selector */}
          <div className="relative hidden sm:block">
            <button
              onClick={() => setSessionOpen(prev => !prev)}
              className="flex items-center gap-1.5 retro-btn-ghost px-2.5 py-1.5 text-xs"
              aria-label="Open saved sessions"
            >
              <BookOpen size={13} />
              <span className="hidden lg:inline font-mono">Sessions</span>
              <ChevronDown size={11} className={`transition-transform duration-150 ${sessionOpen ? 'rotate-180' : ''}`} />
            </button>

            {sessionOpen && (
              <div className="absolute right-0 top-full mt-1 w-72 retro-card z-50 py-1 fade-in">
                <div className="px-3 py-2 border-b border-border">
                  <p className="font-mono text-xs text-muted-foreground tracking-widest uppercase">Saved Sessions</p>
                </div>
                {sessions.length === 0 ? (
                  <p className="px-3 py-3 font-mono text-xs text-muted-foreground">No saved papers yet.</p>
                ) : sessions.map(session => (
                  <Link
                    key={`session-${session.arxivId}`}
                    href={`/executive-briefing-display?id=${encodeURIComponent(session.arxivId)}`}
                    onClick={() => {
                      localStorage.setItem('arxiv-digest:last-arxiv-id', session.arxivId);
                      setActiveArxivId(session.arxivId);
                      setSessionOpen(false);
                    }}
                    className="w-full text-left px-3 py-2 hover:bg-muted transition-colors duration-100 group"
                  >
                    <p className="font-sans text-xs text-foreground truncate group-hover:text-primary transition-colors">{session.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="font-mono text-xs text-primary">{session.arxivId}</span>
                      <span className="font-mono text-xs text-muted-foreground">{session.nChunks} chunks</span>
                    </div>
                  </Link>
                ))}
                <div className="border-t border-border mt-1 px-3 py-2">
                  <button className="font-mono text-xs text-muted-foreground hover:text-foreground transition-colors">
                    View all sessions →
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="retro-btn-ghost p-1.5 rounded-sm"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? (
              <Sun size={15} />
            ) : (
              <Moon size={15} />
            )}
          </button>

          {/* Mobile menu */}
          <button
            onClick={() => setMobileOpen(prev => !prev)}
            className="md:hidden retro-btn-ghost p-1.5 rounded-sm"
            aria-label="Toggle mobile menu"
          >
            {mobileOpen ? <X size={15} /> : <Menu size={15} />}
          </button>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileOpen && (
        <div className="md:hidden bg-card border-t border-border py-2 px-4 fade-in">
          {navLinks.map(link => {
            const Icon = link.icon;
            const isActive = link.href === '/' ? pathname === '/' : pathname === link.href;
            return (
              <Link
                key={`mobile-nav-${link.href}`}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-sm font-mono text-sm font-medium tracking-wide transition-all duration-150 mb-1 ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                <Icon size={15} />
                {link.label}
              </Link>
            );
          })}
        </div>
      )}

      {/* Click outside to close session dropdown */}
      {sessionOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setSessionOpen(false)}
        />
      )}
    </header>
  );
}
