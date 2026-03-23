import { useState, useRef, useEffect } from 'react';
import { useTimelineStore } from '../../stores/timelineStore';
import type { TimelineClip, TransitionType } from '../../types';

const TRANSITION_OPTIONS: { value: TransitionType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'crossfade', label: 'Crossfade' },
  { value: 'fade-from-black', label: 'Fade from Black' },
  { value: 'fade-to-black', label: 'Fade to Black' },
  { value: 'wipe-left', label: 'Wipe Left' },
  { value: 'wipe-right', label: 'Wipe Right' },
];

interface TransitionHandleProps {
  clipBefore: TimelineClip;
  clipAfter: TimelineClip;
  pixelsPerSecond: number;
}

export function TransitionHandle({ clipBefore, clipAfter, pixelsPerSecond }: TransitionHandleProps) {
  const setClipTransition = useTimelineStore((s) => s.setClipTransition);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const gap = clipAfter.startTime - (clipBefore.startTime + clipBefore.duration);
  // Only show if clips are within 0.1s of each other
  if (gap > 0.1) return null;

  const transition = clipAfter.transitionIn;
  const hasTransition = transition && transition.type !== 'none';

  // Position at the junction between the two clips
  const junctionX = clipAfter.startTime * pixelsPerSecond;

  // Transition overlay width (for visual representation)
  const transitionDuration = transition?.duration ?? 0.5;
  const overlapWidth = hasTransition ? transitionDuration * pixelsPerSecond : 0;

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    // Delay to avoid immediate close
    const timer = setTimeout(() => document.addEventListener('mousedown', handleClick), 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClick);
    };
  }, [menuOpen]);

  return (
    <>
      {/* Transition overlap visualization */}
      {hasTransition && (
        <div
          className="absolute top-1 bottom-1 rounded bg-blue-500/20 border border-blue-500/40 pointer-events-none"
          style={{
            left: junctionX - overlapWidth / 2,
            width: overlapWidth,
          }}
        />
      )}

      {/* Diamond handle */}
      <div
        className="absolute top-1/2 z-10 flex -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center"
        style={{ left: junctionX }}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen(!menuOpen);
        }}
      >
        <div
          className={`h-4 w-4 rotate-45 rounded-sm border transition-colors ${
            hasTransition
              ? 'border-blue-400 bg-blue-600 shadow-sm shadow-blue-500/50'
              : 'border-zinc-500 bg-zinc-700 hover:border-zinc-400 hover:bg-zinc-600'
          }`}
        />
      </div>

      {/* Dropdown menu */}
      {menuOpen && (
        <div
          ref={menuRef}
          className="absolute z-50 min-w-[160px] rounded-lg border border-zinc-600 bg-zinc-800 py-1 shadow-xl"
          style={{
            left: junctionX - 80,
            top: '100%',
          }}
        >
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Transition
          </div>
          {TRANSITION_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                if (opt.value === 'none') {
                  setClipTransition(clipAfter.id, undefined);
                } else {
                  setClipTransition(clipAfter.id, {
                    type: opt.value,
                    duration: transition?.duration ?? 0.5,
                  });
                }
                setMenuOpen(false);
              }}
              className={`flex w-full items-center px-3 py-1.5 text-xs hover:bg-zinc-700 ${
                (transition?.type === opt.value || (!transition && opt.value === 'none'))
                  ? 'text-blue-400'
                  : 'text-zinc-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
