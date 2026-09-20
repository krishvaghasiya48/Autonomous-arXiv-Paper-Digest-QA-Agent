import React, { Suspense } from 'react';
import AppLayout from '@/components/AppLayout';
import QAChatContent from './components/QAChatContent';

export default function QAChatPage() {
  return (
    <AppLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-64 font-mono text-amber-500">LOADING QA SESSION...</div>}>
        <QAChatContent />
      </Suspense>
    </AppLayout>
  );
}