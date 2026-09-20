import React from 'react';
import AppLayout from '@/components/AppLayout';



import SearchStateManager from '@/app/components/SearchStateManager';

export default function PaperSearchPage() {
  return (
    <AppLayout>
      <SearchStateManager />
    </AppLayout>
  );
}