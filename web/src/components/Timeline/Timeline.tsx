import { useRef, useMemo } from 'react';
import { Plus, ZoomIn, ZoomOut } from 'lucide-react';
import { useTimelineStore } from '../../stores/timelineStore';
import { TimeRuler } from './TimeRuler';
import { Playhead } from './Playhead';
import { Track } from './Track';

export function Timeline() {
  const tracks = useTimelineStore((s) => s.tracks);
  const zoom = useTimelineStore((s) => s.zoom);
  const setZoom = useTimelineStore((s) => s.setZoom);
  const setScrollPosition = useTimelineStore((s) => s.setScrollPosition);
  const addTrack = useTimelineStore((s) => s.addTrack);
  const totalDuration = useTimelineStore((s) => s.totalDuration);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pixelsPerSecond = 100 * zoom;

  const duration = totalDuration();
  const minWidth = 2000;
  const timelineWidth = useMemo(
    () => Math.max(minWidth, (duration + 10) * pixelsPerSecond),
    [duration, pixelsPerSecond]
  );

  const trackAreaHeight = tracks.length * 56 + 24; // 56px per track + ruler

  const handleScroll = () => {
    if (scrollContainerRef.current) {
      setScrollPosition(scrollContainerRef.current.scrollLeft);
    }
  };

  return (
    <div className="flex h-full flex-col bg-zinc-850">
      {/* Timeline toolbar */}
      <div className="flex items-center justify-between border-b border-zinc-700 bg-zinc-800 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-zinc-200">Timeline</h2>
          <button
            onClick={() => addTrack('video')}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            title="Add video track"
          >
            <Plus className="h-3 w-3" />
            Video
          </button>
          <button
            onClick={() => addTrack('audio')}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            title="Add audio track"
          >
            <Plus className="h-3 w-3" />
            Audio
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setZoom(zoom / 1.5)}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <input
            type="range"
            min={0.1}
            max={5}
            step={0.1}
            value={zoom}
            onChange={(e) => setZoom(parseFloat(e.target.value))}
            className="h-1 w-24 cursor-pointer accent-blue-500"
          />
          <button
            onClick={() => setZoom(zoom * 1.5)}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <span className="min-w-[3rem] text-right text-[10px] text-zinc-500">
            {Math.round(zoom * 100)}%
          </span>
        </div>
      </div>

      {/* Scrollable timeline area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-auto"
        onScroll={handleScroll}
      >
        <div className="relative" style={{ width: timelineWidth + 160 }}>
          {/* Time ruler (offset by track header width) */}
          <div className="flex">
            <div className="w-40 shrink-0 border-b border-r border-zinc-700 bg-zinc-800" />
            <TimeRuler width={timelineWidth} pixelsPerSecond={pixelsPerSecond} />
          </div>

          {/* Tracks */}
          <div className="relative">
            {tracks.map((track) => (
              <Track
                key={track.id}
                track={track}
                pixelsPerSecond={pixelsPerSecond}
                timelineWidth={timelineWidth}
              />
            ))}

            {/* Playhead overlay (spans all tracks) */}
            <div
              className="pointer-events-none absolute top-0 left-40"
              style={{ height: trackAreaHeight }}
            >
              <Playhead
                pixelsPerSecond={pixelsPerSecond}
                height={tracks.length * 56}
              />
            </div>
          </div>

          {/* Empty area for dropping clips */}
          {tracks.length === 0 && (
            <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
              Add a track to get started
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
