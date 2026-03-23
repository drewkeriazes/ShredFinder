import { useDraggable } from '@dnd-kit/core';
import { Film, Zap, RotateCcw, Gauge, AlertTriangle } from 'lucide-react';
import type { DetectedClip } from '../../types';

const TYPE_COLORS: Record<string, string> = {
  jump: 'bg-blue-500',
  spin: 'bg-purple-500',
  speed: 'bg-green-500',
  crash: 'bg-red-500',
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  jump: <Zap className="h-3 w-3" />,
  spin: <RotateCcw className="h-3 w-3" />,
  speed: <Gauge className="h-3 w-3" />,
  crash: <AlertTriangle className="h-3 w-3" />,
};

function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}:${String(sec).padStart(2, '0')}` : `${sec}s`;
}

function getKeyStat(clip: DetectedClip): string {
  if (clip.type === 'jump' && clip.metadata.airtime != null) {
    return `${clip.metadata.airtime.toFixed(1)}s air`;
  }
  if (clip.type === 'spin' && clip.metadata.rotation != null) {
    return `${clip.metadata.rotation}\u00B0`;
  }
  if (clip.type === 'speed' && clip.metadata.speed != null) {
    return `${Math.round(clip.metadata.speed)}mph`;
  }
  if (clip.type === 'crash') {
    return 'crash';
  }
  return `${Math.round(clip.confidence * 100)}%`;
}

interface ClipCardProps {
  clip: DetectedClip & { mediaFilename: string };
}

export function ClipCard({ clip }: ClipCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: clip.id,
      data: { clip },
    });

  const style = transform
    ? {
        transform: `translate(${transform.x}px, ${transform.y}px)`,
        opacity: isDragging ? 0.5 : 1,
      }
    : undefined;

  const duration = clip.endTime - clip.startTime;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="group cursor-grab rounded-lg border border-zinc-700 bg-zinc-800 transition hover:border-zinc-500 active:cursor-grabbing"
    >
      {/* Thumbnail area */}
      <div className="relative aspect-video w-full overflow-hidden rounded-t-lg bg-zinc-700">
        <div className="flex h-full items-center justify-center text-zinc-500">
          <Film className="h-8 w-8" />
        </div>

        {/* Type badge */}
        <span
          className={`absolute left-1.5 top-1.5 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold text-white ${TYPE_COLORS[clip.type]}`}
        >
          {TYPE_ICONS[clip.type]}
          {clip.type}
        </span>

        {/* Duration badge */}
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-200">
          {formatDuration(duration)}
        </span>
      </div>

      {/* Info */}
      <div className="px-2 py-1.5">
        <p className="truncate text-xs font-medium text-zinc-300">
          {clip.mediaFilename}
        </p>
        <div className="mt-0.5 flex items-center justify-between">
          <span className="text-[10px] text-zinc-500">{getKeyStat(clip)}</span>
          {clip.metadata.landingQuality && (
            <span
              className={`rounded px-1 py-0.5 text-[10px] font-medium ${
                clip.metadata.landingQuality === 'clean'
                  ? 'bg-green-500/20 text-green-400'
                  : clip.metadata.landingQuality === 'sketchy'
                    ? 'bg-yellow-500/20 text-yellow-400'
                    : 'bg-red-500/20 text-red-400'
              }`}
            >
              {clip.metadata.landingQuality}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
