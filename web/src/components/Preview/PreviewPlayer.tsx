import { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  Maximize,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { useTimelineStore } from '../../stores/timelineStore';
import { useMediaStore } from '../../stores/mediaStore';
import { mediaApi } from '../../services/api';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const f = Math.floor((seconds % 1) * 30);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(f).padStart(2, '0')}`;
}

export function PreviewPlayer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isPlaying = useTimelineStore((s) => s.isPlaying);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const togglePlay = useTimelineStore((s) => s.togglePlay);
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const totalDuration = useTimelineStore((s) => s.totalDuration);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const selectedClipId = useTimelineStore((s) => s.selectedClipId);
  const tracks = useTimelineStore((s) => s.tracks);
  const mediaFiles = useMediaStore((s) => s.mediaFiles);

  const duration = totalDuration();

  // Find the selected clip or the clip under the playhead
  const activeClip = useMemo(() => {
    if (selectedClipId) {
      for (const track of tracks) {
        const found = track.clips.find((c) => c.id === selectedClipId);
        if (found) return found;
      }
    }
    // Fallback: find clip under playhead on any video track
    for (const track of tracks) {
      if (track.type !== 'video') continue;
      const found = track.clips.find(
        (c) =>
          playheadPosition >= c.startTime &&
          playheadPosition < c.startTime + c.duration
      );
      if (found) return found;
    }
    return null;
  }, [selectedClipId, tracks, playheadPosition]);

  // Preview from library selection
  const previewMediaId = useMediaStore((s) => s.previewMediaId);

  // Resolve media URL: timeline clip takes priority, then library preview
  const videoSrc = useMemo(() => {
    if (activeClip) {
      const media = mediaFiles.find((m) => m.id === activeClip.mediaId);
      if (media) {
        return mediaApi.streamUrl(media.id);
      }
      return mediaApi.streamUrl(activeClip.mediaId);
    }
    if (previewMediaId) {
      return mediaApi.streamUrl(previewMediaId);
    }
    return '';
  }, [activeClip, mediaFiles, previewMediaId]);

  // Update video src when active clip changes
  useEffect(() => {
    if (!videoRef.current) return;
    const currentSrc = videoRef.current.src;
    if (videoSrc && currentSrc !== videoSrc) {
      videoRef.current.src = videoSrc;
      videoRef.current.load();
    } else if (!videoSrc && currentSrc) {
      videoRef.current.removeAttribute('src');
      videoRef.current.load();
    }
  }, [videoSrc]);

  // Sync video currentTime to match clip position relative to playhead
  useEffect(() => {
    if (!videoRef.current || !activeClip || !videoSrc) return;
    const clipOffset = playheadPosition - activeClip.startTime;
    const mediaTime = activeClip.trimStart + clipOffset;
    if (Math.abs(videoRef.current.currentTime - mediaTime) > 0.1) {
      videoRef.current.currentTime = mediaTime;
    }
  }, [playheadPosition, activeClip, videoSrc]);

  useEffect(() => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.play().catch(() => {});
      } else {
        videoRef.current.pause();
      }
    }
  }, [isPlaying]);

  const handleSkipBack = useCallback(() => {
    setPlayhead(Math.max(0, playheadPosition - 5));
  }, [playheadPosition, setPlayhead]);

  const handleSkipForward = useCallback(() => {
    setPlayhead(playheadPosition + 5);
  }, [playheadPosition, setPlayhead]);

  const handleFrameBack = useCallback(() => {
    setPlayhead(Math.max(0, playheadPosition - 1 / 30));
  }, [playheadPosition, setPlayhead]);

  const handleFrameForward = useCallback(() => {
    setPlayhead(playheadPosition + 1 / 30);
  }, [playheadPosition, setPlayhead]);

  const handleFullscreen = useCallback(() => {
    if (containerRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        containerRef.current.requestFullscreen();
      }
    }
  }, []);

  return (
    <div ref={containerRef} className="flex h-full flex-col bg-zinc-900">
      {/* Header */}
      <div className="flex items-center border-b border-zinc-700 px-3 py-2">
        <h2 className="text-sm font-semibold text-zinc-200">Preview</h2>
      </div>

      {/* Video area */}
      <div className="relative flex flex-1 items-center justify-center bg-black">
        <video
          ref={videoRef}
          className="max-h-full max-w-full"
          muted={muted}
        />
        {/* Placeholder when no video */}
        {!videoSrc && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-zinc-600">
              <Play className="mx-auto mb-2 h-12 w-12" />
              <p className="text-sm">Select a clip to preview</p>
            </div>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="border-t border-zinc-700 bg-zinc-800 px-3 py-2">
        {/* Progress bar */}
        <div
          className="group mb-2 h-1 cursor-pointer rounded-full bg-zinc-700"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            setPlayhead(pct * duration);
          }}
        >
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{
              width: duration > 0 ? `${(playheadPosition / duration) * 100}%` : '0%',
            }}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <button
              onClick={handleSkipBack}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              title="Skip back 5s"
            >
              <SkipBack className="h-4 w-4" />
            </button>
            <button
              onClick={handleFrameBack}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              title="Previous frame"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={togglePlay}
              className="rounded-full bg-zinc-700 p-1.5 text-zinc-200 hover:bg-zinc-600"
              title="Play/Pause (Space)"
            >
              {isPlaying ? (
                <Pause className="h-4 w-4" />
              ) : (
                <Play className="h-4 w-4" />
              )}
            </button>
            <button
              onClick={handleFrameForward}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              title="Next frame"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <button
              onClick={handleSkipForward}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              title="Skip forward 5s"
            >
              <SkipForward className="h-4 w-4" />
            </button>
          </div>

          {/* Time display */}
          <span className="font-mono text-xs text-zinc-400">
            {formatTime(playheadPosition)} / {formatTime(duration)}
          </span>

          <div className="flex items-center gap-1">
            {/* Volume */}
            <button
              onClick={() => setMuted(!muted)}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            >
              {muted ? (
                <VolumeX className="h-4 w-4" />
              ) : (
                <Volume2 className="h-4 w-4" />
              )}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={muted ? 0 : volume}
              onChange={(e) => {
                setVolume(parseFloat(e.target.value));
                if (muted) setMuted(false);
              }}
              className="h-1 w-16 cursor-pointer accent-blue-500"
            />

            {/* Fullscreen */}
            <button
              onClick={handleFullscreen}
              className="rounded p-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              title="Fullscreen"
            >
              <Maximize className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
