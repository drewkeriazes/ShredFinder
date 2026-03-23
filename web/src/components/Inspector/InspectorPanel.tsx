import { useTimelineStore } from '../../stores/timelineStore';
import { Settings, Film, Music, Scissors } from 'lucide-react';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const f = Math.floor((seconds % 1) * 30);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(f).padStart(2, '0')}`;
}

export function InspectorPanel() {
  const selectedClipId = useTimelineStore((s) => s.selectedClipId);
  const getSelectedClip = useTimelineStore((s) => s.getSelectedClip);
  const trimClip = useTimelineStore((s) => s.trimClip);
  const updateClip = useTimelineStore((s) => s.updateClip);

  const clip = getSelectedClip();

  if (!selectedClipId || !clip) {
    return (
      <div className="flex h-full flex-col bg-zinc-850">
        <div className="flex items-center border-b border-zinc-700 px-3 py-2">
          <Settings className="mr-2 h-4 w-4 text-zinc-500" />
          <h2 className="text-sm font-semibold text-zinc-200">Inspector</h2>
        </div>
        <div className="flex flex-1 items-center justify-center p-4">
          <p className="text-center text-sm text-zinc-500">
            Select a clip on the timeline to inspect its properties
          </p>
        </div>
      </div>
    );
  }

  const TYPE_COLOR: Record<string, string> = {
    jump: 'text-blue-400',
    spin: 'text-purple-400',
    speed: 'text-green-400',
    crash: 'text-red-400',
    custom: 'text-zinc-400',
  };

  return (
    <div className="flex h-full flex-col bg-zinc-850">
      {/* Header */}
      <div className="flex items-center border-b border-zinc-700 px-3 py-2">
        <Settings className="mr-2 h-4 w-4 text-zinc-500" />
        <h2 className="text-sm font-semibold text-zinc-200">Inspector</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {/* Clip info */}
        <section className="mb-4">
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            {clip.type === 'custom' ? (
              <Film className="h-3.5 w-3.5" />
            ) : (
              <Scissors className="h-3.5 w-3.5" />
            )}
            Clip Info
          </h3>
          <div className="space-y-2 rounded-lg bg-zinc-800 p-3">
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Name</span>
              <span className="text-xs text-zinc-300">{clip.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Type</span>
              <span className={`text-xs font-medium capitalize ${TYPE_COLOR[clip.type]}`}>
                {clip.type}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Duration</span>
              <span className="text-xs text-zinc-300">
                {formatTime(clip.duration)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Position</span>
              <span className="text-xs text-zinc-300">
                {formatTime(clip.startTime)}
              </span>
            </div>
          </div>
        </section>

        {/* Trim controls */}
        <section className="mb-4">
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <Scissors className="h-3.5 w-3.5" />
            Trim
          </h3>
          <div className="space-y-2 rounded-lg bg-zinc-800 p-3">
            <div>
              <label className="mb-1 block text-[10px] text-zinc-500">
                Trim Start (s)
              </label>
              <input
                type="number"
                min={0}
                step={0.1}
                value={clip.trimStart}
                onChange={(e) =>
                  trimClip(clip.id, parseFloat(e.target.value) || 0, clip.trimEnd)
                }
                className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-zinc-500">
                Trim End (s)
              </label>
              <input
                type="number"
                min={0}
                step={0.1}
                value={clip.trimEnd}
                onChange={(e) =>
                  trimClip(clip.id, clip.trimStart, parseFloat(e.target.value) || 0)
                }
                className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </section>

        {/* Speed */}
        <section className="mb-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Speed
          </h3>
          <div className="rounded-lg bg-zinc-800 p-3">
            <div>
              <label className="mb-1 block text-[10px] text-zinc-500">
                Multiplier
              </label>
              <input
                type="number"
                min={0.1}
                max={4}
                step={0.1}
                value={clip.speed ?? 1}
                onChange={(e) =>
                  updateClip(clip.id, { speed: parseFloat(e.target.value) || 1 })
                }
                className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </section>

        {/* Volume */}
        <section className="mb-4">
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            <Music className="h-3.5 w-3.5" />
            Audio
          </h3>
          <div className="space-y-2 rounded-lg bg-zinc-800 p-3">
            <div>
              <label className="mb-1 block text-[10px] text-zinc-500">
                Volume ({clip.volume ?? 100}%)
              </label>
              <input
                type="range"
                min={0}
                max={200}
                value={clip.volume ?? 100}
                onChange={(e) =>
                  updateClip(clip.id, { volume: parseInt(e.target.value, 10) })
                }
                className="w-full cursor-pointer accent-blue-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] text-zinc-500">
                Opacity ({clip.opacity ?? 100}%)
              </label>
              <input
                type="range"
                min={0}
                max={100}
                value={clip.opacity ?? 100}
                onChange={(e) =>
                  updateClip(clip.id, { opacity: parseInt(e.target.value, 10) })
                }
                className="w-full cursor-pointer accent-blue-500"
              />
            </div>
          </div>
        </section>

        {/* Transform (placeholder) */}
        <section className="mb-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Transform
          </h3>
          <div className="space-y-2 rounded-lg bg-zinc-800 p-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[10px] text-zinc-500">
                  Position X
                </label>
                <input
                  type="number"
                  defaultValue={0}
                  className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] text-zinc-500">
                  Position Y
                </label>
                <input
                  type="number"
                  defaultValue={0}
                  className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] text-zinc-500">
                  Scale
                </label>
                <input
                  type="number"
                  defaultValue={100}
                  min={1}
                  className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] text-zinc-500">
                  Rotation
                </label>
                <input
                  type="number"
                  defaultValue={0}
                  className="w-full rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Effects placeholder */}
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Effects
          </h3>
          <div className="rounded-lg border border-dashed border-zinc-700 p-4 text-center">
            <p className="text-xs text-zinc-500">No effects applied</p>
          </div>
        </section>
      </div>
    </div>
  );
}
