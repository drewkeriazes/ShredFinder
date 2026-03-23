import { useMemo } from 'react';
import {
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Volume2,
  VolumeX,
  Film,
  Music,
  Headphones,
} from 'lucide-react';
import { useTimelineStore } from '../../stores/timelineStore';
import { TimelineClipComponent } from './TimelineClip';
import { TransitionHandle } from './TransitionHandle';
import type { Track as TrackType } from '../../types';

interface TrackProps {
  track: TrackType;
  pixelsPerSecond: number;
  timelineWidth: number;
}

export function Track({ track, pixelsPerSecond, timelineWidth }: TrackProps) {
  const toggleTrackMute = useTimelineStore((s) => s.toggleTrackMute);
  const toggleTrackLock = useTimelineStore((s) => s.toggleTrackLock);
  const toggleTrackVisibility = useTimelineStore((s) => s.toggleTrackVisibility);
  const soloTrack = useTimelineStore((s) => s.soloTrack);

  // Sort clips by startTime for transition handles
  const sortedClips = useMemo(
    () => [...track.clips].sort((a, b) => a.startTime - b.startTime),
    [track.clips]
  );

  return (
    <div className="flex border-b border-zinc-700">
      {/* Track header */}
      <div className="flex w-40 shrink-0 items-center gap-1 border-r border-zinc-700 bg-zinc-800 px-2 py-1">
        {track.type === 'video' ? (
          <Film className="h-3.5 w-3.5 text-blue-400" />
        ) : (
          <Music className="h-3.5 w-3.5 text-green-400" />
        )}
        <span className="flex-1 truncate text-xs font-medium text-zinc-300">
          {track.name}
        </span>
        <div className="flex gap-0.5">
          <button
            onClick={() => soloTrack(track.id)}
            className="rounded p-0.5 text-zinc-500 hover:text-zinc-300"
            title="Solo"
          >
            <Headphones className="h-3 w-3" />
          </button>
          <button
            onClick={() => toggleTrackMute(track.id)}
            className="rounded p-0.5 text-zinc-500 hover:text-zinc-300"
            title={track.muted ? 'Unmute' : 'Mute'}
          >
            {track.muted ? (
              <VolumeX className="h-3 w-3 text-red-400" />
            ) : (
              <Volume2 className="h-3 w-3" />
            )}
          </button>
          <button
            onClick={() => toggleTrackLock(track.id)}
            className="rounded p-0.5 text-zinc-500 hover:text-zinc-300"
            title={track.locked ? 'Unlock' : 'Lock'}
          >
            {track.locked ? (
              <Lock className="h-3 w-3 text-yellow-400" />
            ) : (
              <Unlock className="h-3 w-3" />
            )}
          </button>
          <button
            onClick={() => toggleTrackVisibility(track.id)}
            className="rounded p-0.5 text-zinc-500 hover:text-zinc-300"
            title={track.visible ? 'Hide' : 'Show'}
          >
            {track.visible ? (
              <Eye className="h-3 w-3" />
            ) : (
              <EyeOff className="h-3 w-3 text-zinc-600" />
            )}
          </button>
        </div>
      </div>

      {/* Track content area */}
      <div
        className="relative h-14 bg-zinc-900/50"
        style={{ width: timelineWidth }}
      >
        {/* Grid lines (subtle) */}
        <div className="pointer-events-none absolute inset-0 opacity-10">
          {Array.from({ length: Math.ceil(timelineWidth / (pixelsPerSecond * 5)) }, (_, i) => (
            <div
              key={i}
              className="absolute top-0 bottom-0 w-px bg-zinc-400"
              style={{ left: i * pixelsPerSecond * 5 }}
            />
          ))}
        </div>

        {/* Clips */}
        {sortedClips.map((clip) => (
          <TimelineClipComponent
            key={clip.id}
            clip={clip}
            pixelsPerSecond={pixelsPerSecond}
            trackLocked={track.locked}
          />
        ))}

        {/* Transition handles between adjacent clips */}
        {sortedClips.map((clip, i) => {
          if (i === 0) return null;
          const prev = sortedClips[i - 1];
          return (
            <TransitionHandle
              key={`transition-${prev.id}-${clip.id}`}
              clipBefore={prev}
              clipAfter={clip}
              pixelsPerSecond={pixelsPerSecond}
            />
          );
        })}
      </div>
    </div>
  );
}
