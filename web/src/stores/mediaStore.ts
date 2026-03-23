import { create } from 'zustand';
import type { MediaFile, DetectedClip } from '../types';
import { mediaApi, detectionApi } from '../services/api';

type ClipFilter = 'all' | 'jump' | 'spin' | 'speed' | 'crash';
type SortBy = 'confidence' | 'duration' | 'type';

interface MediaState {
  mediaFiles: MediaFile[];
  loading: boolean;
  error: string | null;
  selectedFilter: ClipFilter;
  sortBy: SortBy;
  uploadProgress: Record<string, number>;
  detectionStatus: Record<string, 'queued' | 'running' | 'done' | 'error'>;
  fetchMedia: () => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
  deleteMedia: (id: string) => Promise<void>;
  runDetection: (mediaId: string) => Promise<void>;
  fetchDetectionResults: (mediaId: string) => Promise<void>;
  pollDetectionStatus: (mediaId: string) => Promise<void>;
  setFilter: (filter: ClipFilter) => void;
  setSortBy: (sort: SortBy) => void;
  allClips: () => (DetectedClip & { mediaFilename: string })[];
  filteredClips: () => (DetectedClip & { mediaFilename: string })[];
}

export const useMediaStore = create<MediaState>()((set, get) => ({
  mediaFiles: [],
  loading: false,
  error: null,
  selectedFilter: 'all',
  sortBy: 'confidence',
  uploadProgress: {},
  detectionStatus: {},

  fetchMedia: async () => {
    set({ loading: true, error: null });
    try {
      const res = await mediaApi.list();
      set({ mediaFiles: res.items, loading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch media',
        loading: false,
      });
    }
  },

  uploadFile: async (file) => {
    const tempId = `upload-${Date.now()}`;
    set((state) => ({
      uploadProgress: { ...state.uploadProgress, [tempId]: 0 },
    }));
    try {
      const media = await mediaApi.upload(file, (pct) => {
        set((state) => ({
          uploadProgress: { ...state.uploadProgress, [tempId]: pct },
        }));
      });
      set((state) => {
        const { [tempId]: _, ...rest } = state.uploadProgress;
        void _;
        return {
          mediaFiles: [...state.mediaFiles, media],
          uploadProgress: rest,
        };
      });
    } catch (err) {
      set((state) => {
        const { [tempId]: _, ...rest } = state.uploadProgress;
        void _;
        return {
          uploadProgress: rest,
          error: err instanceof Error ? err.message : 'Upload failed',
        };
      });
    }
  },

  deleteMedia: async (id) => {
    try {
      await mediaApi.delete(id);
      set((state) => ({
        mediaFiles: state.mediaFiles.filter((m) => m.id !== id),
      }));
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to delete media',
      });
    }
  },

  runDetection: async (mediaId) => {
    try {
      set((state) => ({
        detectionStatus: { ...state.detectionStatus, [mediaId]: 'running' as const },
      }));
      await detectionApi.run(mediaId);
      await get().pollDetectionStatus(mediaId);
    } catch (err) {
      set((state) => ({
        detectionStatus: { ...state.detectionStatus, [mediaId]: 'error' as const },
        error: err instanceof Error ? err.message : 'Detection failed',
      }));
    }
  },

  fetchDetectionResults: async (mediaId) => {
    try {
      const result = await detectionApi.results(mediaId);
      set((state) => ({
        mediaFiles: state.mediaFiles.map((mf) =>
          mf.id === mediaId
            ? { ...mf, clips: result.clips, status: 'ready' as const }
            : mf
        ),
        detectionStatus: { ...state.detectionStatus, [mediaId]: 'done' as const },
      }));
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch detection results',
      });
    }
  },

  pollDetectionStatus: async (mediaId) => {
    const poll = (): Promise<void> =>
      new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
          try {
            const result = await detectionApi.status(mediaId);
            set((state) => ({
              detectionStatus: { ...state.detectionStatus, [mediaId]: result.status },
            }));
            if (result.status === 'done') {
              clearInterval(interval);
              await get().fetchDetectionResults(mediaId);
              resolve();
            } else if (result.status === 'error') {
              clearInterval(interval);
              set({ error: 'Detection failed on server' });
              reject(new Error('Detection failed'));
            }
          } catch (err) {
            clearInterval(interval);
            reject(err);
          }
        }, 2000);
      });
    await poll();
  },

  setFilter: (filter) => set({ selectedFilter: filter }),
  setSortBy: (sort) => set({ sortBy: sort }),

  allClips: () => {
    const { mediaFiles } = get();
    return mediaFiles.flatMap((mf) =>
      mf.clips.map((c) => ({ ...c, mediaFilename: mf.filename }))
    );
  },

  filteredClips: () => {
    const { selectedFilter, sortBy } = get();
    let clips = get().allClips();

    if (selectedFilter !== 'all') {
      clips = clips.filter((c) => c.type === selectedFilter);
    }

    clips.sort((a, b) => {
      switch (sortBy) {
        case 'confidence':
          return b.confidence - a.confidence;
        case 'duration':
          return (b.endTime - b.startTime) - (a.endTime - a.startTime);
        case 'type':
          return a.type.localeCompare(b.type);
        default:
          return 0;
      }
    });

    return clips;
  },
}));
