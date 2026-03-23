import { create } from 'zustand';
import type { Track, TimelineClip } from '../types';

interface HistoryEntry {
  tracks: Track[];
  playheadPosition: number;
}

interface TimelineState {
  tracks: Track[];
  playheadPosition: number;
  isPlaying: boolean;
  zoom: number;
  scrollPosition: number;
  selectedClipId: string | null;
  history: HistoryEntry[];
  historyIndex: number;

  // Track actions
  addTrack: (type: 'video' | 'audio') => void;
  removeTrack: (id: string) => void;
  toggleTrackMute: (id: string) => void;
  toggleTrackLock: (id: string) => void;
  toggleTrackVisibility: (id: string) => void;

  // Clip actions
  addClip: (trackId: string, clip: Omit<TimelineClip, 'id' | 'trackId'>) => void;
  removeClip: (id: string) => void;
  moveClip: (id: string, trackId: string, startTime: number) => void;
  trimClip: (id: string, trimStart: number, trimEnd: number) => void;
  splitClip: (id: string, position: number) => void;
  selectClip: (id: string | null) => void;
  updateClip: (id: string, partial: Partial<Pick<TimelineClip, 'speed' | 'volume' | 'opacity'>>) => void;

  // Playback
  setPlayhead: (time: number) => void;
  play: () => void;
  pause: () => void;
  togglePlay: () => void;

  // View
  setZoom: (zoom: number) => void;
  setScrollPosition: (pos: number) => void;

  // History
  undo: () => void;
  redo: () => void;
  pushHistory: () => void;

  // Computed
  totalDuration: () => number;
  getSelectedClip: () => TimelineClip | null;
}

let trackCounter = 0;
let clipCounter = 0;

function genTrackId(): string {
  return `track-${++trackCounter}-${Date.now()}`;
}

function genClipId(): string {
  return `clip-${++clipCounter}-${Date.now()}`;
}

export const useTimelineStore = create<TimelineState>()((set, get) => ({
  tracks: [
    {
      id: 'v1',
      name: 'Video 1',
      type: 'video',
      clips: [],
      muted: false,
      locked: false,
      visible: true,
    },
    {
      id: 'a1',
      name: 'Audio 1',
      type: 'audio',
      clips: [],
      muted: false,
      locked: false,
      visible: true,
    },
  ],
  playheadPosition: 0,
  isPlaying: false,
  zoom: 1,
  scrollPosition: 0,
  selectedClipId: null,
  history: [],
  historyIndex: -1,

  addTrack: (type) => {
    get().pushHistory();
    const id = genTrackId();
    const name = type === 'video' ? `Video ${get().tracks.filter((t) => t.type === 'video').length + 1}` : `Audio ${get().tracks.filter((t) => t.type === 'audio').length + 1}`;
    set((state) => ({
      tracks: [
        ...state.tracks,
        { id, name, type, clips: [], muted: false, locked: false, visible: true },
      ],
    }));
  },

  removeTrack: (id) => {
    get().pushHistory();
    set((state) => ({
      tracks: state.tracks.filter((t) => t.id !== id),
    }));
  },

  toggleTrackMute: (id) => {
    set((state) => ({
      tracks: state.tracks.map((t) =>
        t.id === id ? { ...t, muted: !t.muted } : t
      ),
    }));
  },

  toggleTrackLock: (id) => {
    set((state) => ({
      tracks: state.tracks.map((t) =>
        t.id === id ? { ...t, locked: !t.locked } : t
      ),
    }));
  },

  toggleTrackVisibility: (id) => {
    set((state) => ({
      tracks: state.tracks.map((t) =>
        t.id === id ? { ...t, visible: !t.visible } : t
      ),
    }));
  },

  addClip: (trackId, clip) => {
    get().pushHistory();
    const id = genClipId();
    set((state) => ({
      tracks: state.tracks.map((t) =>
        t.id === trackId
          ? {
              ...t,
              clips: [
                ...t.clips,
                { ...clip, speed: clip.speed ?? 1, volume: clip.volume ?? 100, opacity: clip.opacity ?? 100, id, trackId },
              ],
            }
          : t
      ),
    }));
  },

  removeClip: (id) => {
    get().pushHistory();
    set((state) => ({
      tracks: state.tracks.map((t) => ({
        ...t,
        clips: t.clips.filter((c) => c.id !== id),
      })),
      selectedClipId: state.selectedClipId === id ? null : state.selectedClipId,
    }));
  },

  moveClip: (id, trackId, startTime) => {
    get().pushHistory();
    set((state) => {
      let clip: TimelineClip | null = null;
      const tracksWithout = state.tracks.map((t) => {
        const found = t.clips.find((c) => c.id === id);
        if (found) clip = { ...found, trackId, startTime };
        return { ...t, clips: t.clips.filter((c) => c.id !== id) };
      });

      if (!clip) return state;

      return {
        tracks: tracksWithout.map((t) =>
          t.id === trackId ? { ...t, clips: [...t.clips, clip!] } : t
        ),
      };
    });
  },

  trimClip: (id, trimStart, trimEnd) => {
    get().pushHistory();
    set((state) => ({
      tracks: state.tracks.map((t) => ({
        ...t,
        clips: t.clips.map((c) =>
          c.id === id ? { ...c, trimStart, trimEnd } : c
        ),
      })),
    }));
  },

  splitClip: (id, position) => {
    get().pushHistory();
    set((state) => {
      const newTracks = state.tracks.map((t) => {
        const clipIndex = t.clips.findIndex((c) => c.id === id);
        if (clipIndex === -1) return t;

        const clip = t.clips[clipIndex];
        const relativePos = position - clip.startTime;
        if (relativePos <= 0 || relativePos >= clip.duration) return t;

        const left: TimelineClip = {
          ...clip,
          duration: relativePos,
          trimEnd: clip.trimEnd + (clip.duration - relativePos),
        };

        const right: TimelineClip = {
          ...clip,
          id: genClipId(),
          startTime: position,
          duration: clip.duration - relativePos,
          trimStart: clip.trimStart + relativePos,
        };

        const newClips = [...t.clips];
        newClips.splice(clipIndex, 1, left, right);
        return { ...t, clips: newClips };
      });

      return { tracks: newTracks };
    });
  },

  selectClip: (id) => set({ selectedClipId: id }),

  updateClip: (id, partial) => {
    get().pushHistory();
    set((state) => ({
      tracks: state.tracks.map((t) => ({
        ...t,
        clips: t.clips.map((c) =>
          c.id === id ? { ...c, ...partial } : c
        ),
      })),
    }));
  },

  setPlayhead: (time) => set({ playheadPosition: Math.max(0, time) }),

  play: () => set({ isPlaying: true }),
  pause: () => set({ isPlaying: false }),
  togglePlay: () => set((state) => ({ isPlaying: !state.isPlaying })),

  setZoom: (zoom) => set({ zoom: Math.max(0.1, Math.min(10, zoom)) }),
  setScrollPosition: (pos) => set({ scrollPosition: pos }),

  pushHistory: () => {
    const { tracks, playheadPosition, history, historyIndex } = get();
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push({
      tracks: JSON.parse(JSON.stringify(tracks)),
      playheadPosition,
    });
    if (newHistory.length > 50) newHistory.shift();
    set({ history: newHistory, historyIndex: newHistory.length - 1 });
  },

  undo: () => {
    const { historyIndex, history } = get();
    if (historyIndex < 0) return;
    const entry = history[historyIndex];
    set({
      tracks: entry.tracks,
      playheadPosition: entry.playheadPosition,
      historyIndex: historyIndex - 1,
    });
  },

  redo: () => {
    const { historyIndex, history } = get();
    if (historyIndex >= history.length - 1) return;
    const entry = history[historyIndex + 1];
    set({
      tracks: entry.tracks,
      playheadPosition: entry.playheadPosition,
      historyIndex: historyIndex + 1,
    });
  },

  totalDuration: () => {
    const { tracks } = get();
    let maxEnd = 0;
    for (const track of tracks) {
      for (const clip of track.clips) {
        const end = clip.startTime + clip.duration;
        if (end > maxEnd) maxEnd = end;
      }
    }
    return maxEnd;
  },

  getSelectedClip: () => {
    const { tracks, selectedClipId } = get();
    if (!selectedClipId) return null;
    for (const track of tracks) {
      const clip = track.clips.find((c) => c.id === selectedClipId);
      if (clip) return clip;
    }
    return null;
  },
}));
