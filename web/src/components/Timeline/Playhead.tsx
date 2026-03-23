import { useCallback, useRef, useState } from 'react';
import { useTimelineStore } from '../../stores/timelineStore';

interface PlayheadProps {
  pixelsPerSecond: number;
  height: number;
}

export function Playhead({ pixelsPerSecond, height }: PlayheadProps) {
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const [dragging, setDragging] = useState(false);
  const startXRef = useRef(0);
  const startTimeRef = useRef(0);

  const x = playheadPosition * pixelsPerSecond;

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(true);
      startXRef.current = e.clientX;
      startTimeRef.current = playheadPosition;

      const handleMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startXRef.current;
        const dt = dx / pixelsPerSecond;
        setPlayhead(Math.max(0, startTimeRef.current + dt));
      };

      const handleMouseUp = () => {
        setDragging(false);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [playheadPosition, pixelsPerSecond, setPlayhead]
  );

  return (
    <div
      className="pointer-events-none absolute top-0 z-20"
      style={{ left: x, height }}
    >
      {/* Head */}
      <div
        className="pointer-events-auto relative -left-2 cursor-col-resize"
        onMouseDown={handleMouseDown}
      >
        <svg width="16" height="10" viewBox="0 0 16 10" className="fill-red-500">
          <path d="M0 0 H16 V6 L8 10 L0 6 Z" />
        </svg>
      </div>
      {/* Line */}
      <div
        className={`w-px ${dragging ? 'bg-red-400' : 'bg-red-500'}`}
        style={{ height: height - 10, marginLeft: 7 }}
      />
    </div>
  );
}
