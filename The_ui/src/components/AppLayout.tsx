import React from 'react';
import AppHeader from '@/components/AppHeader';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Toaster } from 'sonner';

interface AppLayoutProps {
  children: React.ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  return (
    <ThemeProvider>
      <div className="min-h-screen bg-background scanline-overlay">
        <AppHeader />
        <main className="max-w-screen-2xl mx-auto px-4 lg:px-8 xl:px-10 2xl:px-16 py-8">
          {children}
        </main>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8rem',
              background: 'var(--card)',
              color: 'var(--foreground)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
            },
          }}
        />
      </div>
    </ThemeProvider>
  );
}