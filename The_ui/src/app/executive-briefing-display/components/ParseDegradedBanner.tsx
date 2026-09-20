import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface ParseDegradedBannerProps {
  parseMethod: string;
}

export default function ParseDegradedBanner({ parseMethod }: ParseDegradedBannerProps) {
  return (
    <div className="warning-banner flex items-start gap-3 p-4 slide-up">
      <AlertTriangle size={16} className="text-warning shrink-0 mt-0.5" />
      <div>
        <p className="font-mono text-sm font-semibold text-warning">
          ⚠ PDF Parsing Degraded — Abstract-Only Analysis
        </p>
        <p className="font-sans text-xs text-warning mt-1 opacity-90 leading-relaxed">
          Both PyMuPDF and pdfplumber failed to extract sufficient text from this PDF
          (likely a scanned or image-based document). This briefing is based on the arXiv
          abstract only. Grounded QA will have limited coverage.{' '}
          <span className="font-mono">parse_method={parseMethod}</span>
        </p>
      </div>
    </div>
  );
}