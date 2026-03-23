import { DndContext } from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { ArrowDownUp, Loader2, Zap } from 'lucide-react';
import { useMediaStore } from '../../stores/mediaStore';
import { useTimelineStore } from '../../stores/timelineStore';
import { ClipCard } from './ClipCard';
import { UploadDropzone } from './UploadDropzone';
import type { DetectedClip } from '../../types';

const FILTERS = [
  { key: 'all' as const, label: 'All' },
  { key: 'jump' as const, label: 'Jumps' },
  { key: 'spin' as const, label: 'Spins' },
  { key: 'speed' as const, label: 'Speed' },
  { key: 'crash' as const, label: 'Crashes' },
];

const SORT_OPTIONS = [
  { key: 'confidence' as const, label: 'Confidence' },
  { key: 'duration' as const, label: 'Duration' },
  { key: 'type' as const, label: 'Type' },
];

export function ClipLibrary() {
  const selectedFilter = useMediaStore((s) => s.selectedFilter);
  const setFilter = useMediaStore((s) => s.setFilter);
  const sortBy = useMediaStore((s) => s.sortBy);
  const setSortBy = useMediaStore((s) => s.setSortBy);
  const filteredClips = useMediaStore((s) => s.filteredClips);
  const mediaFiles = useMediaStore((s) => s.mediaFiles);
  const runDetection = useMediaStore((s) => s.runDetection);
  const detectionStatus = useMediaStore((s) => s.detectionStatus);
  const addClip = useTimelineStore((s) => s.addClip);
  const tracks = useTimelineStore((s) => s.tracks);

  const clips = filteredClips();

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const clip = active.data.current?.clip as
      | (DetectedClip & { mediaFilename: string })
      | undefined;
    if (!clip) return;

    const videoTrack = tracks.find((t) => t.type === 'video');
    if (!videoTrack) return;

    const duration = clip.endTime - clip.startTime;
    const existingEnd = videoTrack.clips.reduce(
      (max, c) => Math.max(max, c.startTime + c.duration),
      0
    );

    addClip(videoTrack.id, {
      mediaId: clip.id,
      startTime: existingEnd,
      duration,
      trimStart: 0,
      trimEnd: 0,
      name: `${clip.type} - ${clip.mediaFilename}`,
      type: clip.type,
      metadata: clip.metadata,
    });
  };

  return (
    <DndContext onDragEnd={handleDragEnd}>
      <div className="flex h-full flex-col bg-zinc-850">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-700 px-3 py-2">
          <h2 className="text-sm font-semibold text-zinc-200">Clip Library</h2>
          <div className="relative">
            <button className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200">
              <ArrowDownUp className="h-3 w-3" />
              {SORT_OPTIONS.find((s) => s.key === sortBy)?.label}
            </button>
            <select
              value={sortBy}
              onChange={(e) =>
                setSortBy(e.target.value as 'confidence' | 'duration' | 'type')
              }
              className="absolute inset-0 cursor-pointer opacity-0"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 border-b border-zinc-700 px-3 py-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition ${
                selectedFilter === f.key
                  ? 'bg-blue-600 text-white'
                  : 'text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Media files with detect buttons */}
        {mediaFiles.length > 0 && (
          <div className="border-b border-zinc-700 px-3 py-2">
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Source Files
            </h3>
            <div className="space-y-1">
              {mediaFiles.map((mf) => {
                const status = detectionStatus[mf.id];
                const isProcessing = status === 'running' || status === 'queued';
                const hasClips = mf.clips.length > 0;
                return (
                  <div
                    key={mf.id}
                    className="flex items-center justify-between rounded bg-zinc-800 px-2 py-1.5"
                  >
                    <span className="truncate text-xs text-zinc-300">
                      {mf.filename}
                    </span>
                    {isProcessing ? (
                      <span className="flex items-center gap-1 text-[10px] text-yellow-400">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Detecting...
                      </span>
                    ) : hasClips ? (
                      <span className="text-[10px] text-green-400">
                        {mf.clips.length} clips
                      </span>
                    ) : (
                      <button
                        onClick={() => runDetection(mf.id)}
                        className="flex items-center gap-1 rounded bg-blue-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-blue-500"
                      >
                        <Zap className="h-3 w-3" />
                        Detect
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Clip grid */}
        <div className="flex-1 overflow-y-auto p-3">
          {clips.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
              <p className="text-sm">No clips found</p>
              <p className="text-xs">Upload footage to get started</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {clips.map((clip) => (
                <ClipCard key={clip.id} clip={clip} />
              ))}
            </div>
          )}
        </div>

        {/* Upload */}
        <UploadDropzone />
      </div>
    </DndContext>
  );
}
