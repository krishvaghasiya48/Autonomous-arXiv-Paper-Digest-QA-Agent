import React from 'react';
import { ArrowLeft, Home } from 'lucide-react';

interface AppIconProps {
  name?: string;
  className?: string;
  size?: number;
}

const iconMap: Record<string, React.ElementType> = {
  ArrowLeftIcon: ArrowLeft,
  HomeIcon: Home,
};

export default function AppIcon({ name, className = '', size = 16 }: AppIconProps) {
  const IconComponent = name ? iconMap[name] : null;
  
  if (IconComponent) {
    return <IconComponent size={size} className={className} />;
  }
  
  return <span className={`inline-block ${className}`}>📄</span>;
}