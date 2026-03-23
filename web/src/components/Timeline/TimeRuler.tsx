import { useTimelineStore } from '../../stores/timelineStore';

function formatTimecode(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return `${m}:${String(s).padStart(2, '0')}`;
  return `${s}s`;
}

interface TimeRulerProps {
  width: number;
  pixelsPerSecond: number;
}

export function TimeRuler({ width, pixelsPerSecond }: TimeRulerProps) {
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const scrollPosition = useTimelineStore((s) => s.scrollPosition);

  // Determine tick interval based on zoom
  let tickInterval = 1; // seconds
  if (pixelsPerSecond < 10) tickInterval = 10;
  else if (pixelsPerSecond < 20) tickInterval = 5;
  else if (pixelsPerSecond < 50) tickInterval = 2;
  else if (pixelsPerSecond > 200) tickInterval = 0.5;

  const totalSeconds = width / pixelsPerSecond;
  const ticks: { time: number; major: boolean }[] = [];

  for (let t = 0; t <= totalSeconds; t += tickInterval) {
    ticks.push({ time: t, major: true });
    // Minor ticks
    if (tickInterval >= 1) {
      for (let m = 1; m < 4; m++) {
        const minor = t + (tickInterval / 4) * m;
        if (minor <= totalSeconds) {
          ticks.push({ time: minor, major: false });
        }
      }
    }
  }

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left + scrollPosition;
    const time = x / pixelsPerSecond;
    setPlayhead(Math.max(0, time));
  };

  return (
    <div
      className="relative h-6 cursor-pointer select-none border-b border-zinc-700 bg-zinc-800"
      onClick={handleClick}
      style={{ width }}
    >
      {ticks.map((tick, i) => {
        const x = tick.time * pixelsPerSecond;
        return (
          <div
            key={i}
            className="absolute top-0"
            style={{ left: x }}
          >
            <div
              className={`${
                tick.major ? 'h-3 bg-zinc-500' : 'h-1.5 bg-zinc-600'
              } w-px`}
              style={{ marginTop: tick.major ? 0 : 6 }}
            />
            {tick.major && (
              <span className="absolute left-1 top-0 text-[9px] text-zinc-500">
                {formatTimecode(tick.time)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
