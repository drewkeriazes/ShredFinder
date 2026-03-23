import { create } from 'zustand';
import type { Project, Track } from '../types';
import { projectsApi } from '../services/api';
import { useTimelineStore } from './timelineStore';

interface ProjectState {
  projects: Project[];
  currentProject: Project | null;
  loading: boolean;
  error: string | null;
  saveTimeout: ReturnType<typeof setTimeout> | null;
  _unsubTimeline: (() => void) | null;
  fetchProjects: () => Promise<void>;
  createProject: (name: string) => Promise<void>;
  openProject: (id: string) => Promise<void>;
  saveProject: () => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  setProjectName: (name: string) => void;
  debouncedSave: () => void;
  _setupTimelineSubscription: () => void;
}

export const useProjectStore = create<ProjectState>()((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,
  error: null,
  saveTimeout: null,
  _unsubTimeline: null,

  fetchProjects: async () => {
    set({ loading: true, error: null });
    try {
      const res = await projectsApi.list();
      set({ projects: res.items, loading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch projects',
        loading: false,
      });
    }
  },

  createProject: async (name) => {
    set({ loading: true, error: null });
    try {
      const project = await projectsApi.create(name);

      // Initialize timeline with default tracks
      useTimelineStore.setState({
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
        zoom: 1,
        selectedClipId: null,
        history: [],
        historyIndex: -1,
        lastModified: Date.now(),
      });

      set((state) => ({
        projects: [...state.projects, project],
        currentProject: project,
        loading: false,
      }));

      // Subscribe to timeline changes for auto-save
      get()._setupTimelineSubscription();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to create project',
        loading: false,
      });
    }
  },

  openProject: async (id) => {
    set({ loading: true, error: null });
    try {
      const project = await projectsApi.get(id);

      // Restore timeline state from project if available
      if (project.timeline_data) {
        try {
          const timelineData = JSON.parse(project.timeline_data) as {
            tracks: Track[];
            playheadPosition: number;
            zoom: number;
          };
          useTimelineStore.setState({
            tracks: timelineData.tracks,
            playheadPosition: timelineData.playheadPosition,
            zoom: timelineData.zoom,
            selectedClipId: null,
            history: [],
            historyIndex: -1,
            lastModified: Date.now(),
          });
        } catch {
          // If parsing fails, keep default timeline state
        }
      } else {
        // No saved timeline data — reset to defaults
        useTimelineStore.setState({
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
          zoom: 1,
          selectedClipId: null,
          history: [],
          historyIndex: -1,
          lastModified: Date.now(),
        });
      }

      set({ currentProject: project, loading: false });

      // Subscribe to timeline changes for auto-save
      get()._setupTimelineSubscription();
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to open project',
        loading: false,
      });
    }
  },

  saveProject: async () => {
    const { currentProject } = get();
    if (!currentProject) return;
    try {
      // Serialize current timeline state
      const timelineState = useTimelineStore.getState();
      const timelineData = JSON.stringify({
        tracks: timelineState.tracks,
        playheadPosition: timelineState.playheadPosition,
        zoom: timelineState.zoom,
      });

      await projectsApi.update(currentProject.id, {
        ...currentProject,
        timeline_data: timelineData,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to save project',
      });
    }
  },

  deleteProject: async (id) => {
    try {
      await projectsApi.delete(id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        currentProject:
          state.currentProject?.id === id ? null : state.currentProject,
      }));
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to delete project',
      });
    }
  },

  setProjectName: (name) => {
    set((state) => ({
      currentProject: state.currentProject
        ? { ...state.currentProject, name }
        : null,
    }));
    get().debouncedSave();
  },

  debouncedSave: () => {
    const { saveTimeout } = get();
    if (saveTimeout) clearTimeout(saveTimeout);
    const timeout = setTimeout(() => {
      get().saveProject();
    }, 2000);
    set({ saveTimeout: timeout });
  },

  // Internal: subscribe to timeline lastModified changes to trigger auto-save
  _setupTimelineSubscription: () => {
    // Unsubscribe previous listener if any
    const prev = get()._unsubTimeline;
    if (prev) prev();

    const unsub = useTimelineStore.subscribe(
      (state, prevState) => {
        if (state.lastModified !== prevState.lastModified && get().currentProject) {
          get().debouncedSave();
        }
      }
    );
    set({ _unsubTimeline: unsub });
  },
}));
