'use client';

import React from 'react';
import QATurnCard from './QATurnCard';
import type { QATurn } from './QAChatContent';

interface QAThreadProps {
  turns: QATurn[];
}

export default function QAThread({ turns }: QAThreadProps) {
  return (
    <div className="space-y-5">
      {turns.map(turn => (
        <QATurnCard key={turn.id} turn={turn} />
      ))}
    </div>
  );
}