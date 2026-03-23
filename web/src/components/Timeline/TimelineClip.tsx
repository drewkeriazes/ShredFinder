import { useCallback, useRef, useState } from 'react';
import { useTimelineStore } from '../../stores/timelineStore';
import type { TimelineClip as TimelineClipType } from '../../types';

const TYPE_COLORS: Record<string, string> = {
  jump: 'bg-blue-600/80 border-blue-500',
  spin: 'bg-purple-600/80 border-purple-500',
  speed: 'bg-green-600/80 border-green-500',
  crash: 'bg-red-600/80 border-red-500',
  custom: 'bg-zinc-600/80 border-zinc-500',
};

interface TimelineClipProps {
  clip: TimelineClipType;
  pixelsPerSecond: number;
  trackLocked?: boolean;
}

export function TimelineClipComponent({ clip, pixelsPerSecond, trackLocked = false }: TimelineClipProps) {
  const selectedClipId = useTimelineStore((s) => s.selectedClipId);
  const selectClip = useTimelineStore((s) => s.selectClip);
  const moveClip = useTimelineStore((s) => s.moveClip);
  const trimClip = useTimelineStore((s) => s.trimClip);
  const removeClip = useTimelineStore((s) => s.removeClip);
  const splitClip = useTimelineStore((s) => s.splitClip);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);

  const isSelected = selectedClipId === clip.id;
  const left = clip.startTime * pixelsPerSecond;
  const width = clip.duration * pixelsPerSecond;
  const colorClass = TYPE_COLORS[clip.type] || TYPE_COLORS.custom;

  const dragRef = useRef({ startX: 0, startTime: 0 });

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      selectClip(clip.id);
      if (trackLocked) return;

      dragRef.current = { startX: e.clientX, startTime: clip.startTime };

      const handleMove = (ev: MouseEvent) => {
        const dx = ev.clientX - dragRef.current.startX;
        const dt = dx / pixelsPerSecond;
        const newStart = Math.max(0, dragRef.current.startTime + dt);
        moveClip(clip.id, clip.trackId, newStart);
      };

      const handleUp = () => {
        document.removeEventListener('mousemove', handleMove);
        document.removeEventListener('mouseup', handleUp);
      };

      document.addEventListener('mousemove', handleMove);
      document.addEventListener('mouseup', handleUp);
    },
    [clip.id, clip.startTime, clip.trackId, pixelsPerSecond, selectClip, moveClip, trackLocked]
  );

  const handleTrimLeft = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (trackLocked) return;
      selectClip(clip.id);
      const startX = e.clientX;
      const origTrimStart = clip.trimStart;

      const handleMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX;
        const dt = dx / pixelsPerSecond;
        trimClip(clip.id, Math.max(0, origTrimStart + dt), clip.trimEnd);
      };

      const handleUp = () => {
        document.removeEventListener('mousemove', handleMove);
        document.removeEventListener('mouseup', handleUp);
      };

      document.addEventListener('mousemove', handleMove);
      document.addEventListener('mouseup', handleUp);
    },
    [clip.id, clip.trimStart, clip.trimEnd, pixelsPerSecond, selectClip, trimClip, trackLocked]
  );

  const handleTrimRight = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (trackLocked) return;
      selectClip(clip.id);
      const startX = e.clientX;
      const origTrimEnd = clip.trimEnd;

      const handleMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX;
        const dt = dx / pixelsPerSecond;
        trimClip(clip.id, clip.trimStart, Math.max(0, origTrimEnd - dt));
      };

      const handleUp = () => {
        document.removeEventListener('mousemove', handleMove);
        document.removeEventListener('mouseup', handleUp);
      };

      document.addEventListener('mousemove', handleMove);
      document.addEventListener('mouseup', handleUp);
    },
    [clip.id, clip.trimStart, clip.trimEnd, pixelsPerSecond, selectClip, trimClip, trackLocked]
  );

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    if (trackLocked) return;
    e.stopPropagation();
    selectClip(clip.id);
    setContextMenu({ x: e.clientX, y: e.clientY });

    const close = () => {
      setContextMenu(null);
      document.removeEventListener('click', close);
    };
    setTimeout(() => document.addEventListener('click', close), 0);
  };

  return (
    <>
      <div
        className={`absolute top-1 bottom-1 flex select-none items-center overflow-hidden rounded border ${colorClass} ${
          isSelected ? 'ring-2 ring-white/50' : ''
        } ${trackLocked ? 'cursor-not-allowed opacity-60' : 'cursor-grab active:cursor-grabbing'}`}
        style={{ left, width: Math.max(width, 4) }}
        onMouseDown={handleMouseDown}
        onContextMenu={handleContextMenu}
      >
        {/* Left trim handle */}
        <div
          className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize bg-white/20 hover:bg-white/40"
          onMouseDown={handleTrimLeft}
        />

        {/* Clip content */}
        <div className="flex-1 truncate px-2 text-[10px] font-medium text-white/90">
          {clip.name}
        </div>

        {/* Right trim handle */}
        <div
          className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize bg-white/20 hover:bg-white/40"
          onMouseDown={handleTrimRight}
        />
      </div>

      {/* Context menu */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[140px] rounded-lg border border-zinc-600 bg-zinc-800 py-1 shadow-xl"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              splitClip(clip.id, playheadPosition);
              setContextMenu(null);
            }}
            className="flex w-full px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Split at Playhead
          </button>
          <button
            onClick={() => {
              // Duplicate: add same clip right after
              const store = useTimelineStore.getState();
              store.addClip(clip.trackId, {
                mediaId: clip.mediaId,
                startTime: clip.startTime + clip.duration,
                duration: clip.duration,
                trimStart: clip.trimStart,
                trimEnd: clip.trimEnd,
                name: clip.name,
                type: clip.type,
                metadata: clip.metadata,
              });
              setContextMenu(null);
            }}
            className="flex w-full px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Duplicate
          </button>
          <div className="my-1 h-px bg-zinc-700" />
          <button
            onClick={() => {
              removeClip(clip.id);
              setContextMenu(null);
            }}
            className="flex w-full px-3 py-1.5 text-xs text-red-400 hover:bg-zinc-700"
          >
            Delete
          </button>
        </div>
      )}
    </>
  );
}
