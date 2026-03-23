import { useMemo } from 'react';
import { useTimelineStore } from '../stores/timelineStore';
import type { TimelineClip } from '../types';

export function useTimeline() {
  const tracks = useTimelineStore((s) => s.tracks);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const totalDuration = useTimelineStore((s) => s.totalDuration);

  const currentClipAtPlayhead = useMemo((): TimelineClip | null => {
    for (const track of tracks) {
      if (!track.visible) continue;
      for (const clip of track.clips) {
        if (
          playheadPosition >= clip.startTime &&
          playheadPosition < clip.startTime + clip.duration
        ) {
          return clip;
        }
      }
    }
    return null;
  }, [tracks, playheadPosition]);

  const duration = totalDuration();

  const snapToEdge = (
    clipId: string,
    proposedStart: number,
    threshold = 0.1
  ): number => {
    const allClips: TimelineClip[] = [];
    for (const track of tracks) {
      for (const clip of track.clips) {
        if (clip.id !== clipId) allClips.push(clip);
      }
    }

    let snappedStart = proposedStart;
    let minDist = threshold;

    for (const other of allClips) {
      const otherEnd = other.startTime + other.duration;

      // Snap start to other clip's end
      const distToEnd = Math.abs(proposedStart - otherEnd);
      if (distToEnd < minDist) {
        snappedStart = otherEnd;
        minDist = distToEnd;
      }

      // Snap start to other clip's start
      const distToStart = Math.abs(proposedStart - other.startTime);
      if (distToStart < minDist) {
        snappedStart = other.startTime;
        minDist = distToStart;
      }
    }

    // Snap to zero
    if (Math.abs(proposedStart) < threshold) {
      snappedStart = 0;
    }

    return snappedStart;
  };

  return {
    currentClipAtPlayhead,
    totalDuration: duration,
    snapToEdge,
  };
}
