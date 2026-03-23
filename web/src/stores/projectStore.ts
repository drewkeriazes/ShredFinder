import { create } from 'zustand';
import type { Project } from '../types';
import { projectsApi } from '../services/api';

interface ProjectState {
  projects: Project[];
  currentProject: Project | null;
  loading: boolean;
  error: string | null;
  saveTimeout: ReturnType<typeof setTimeout> | null;
  fetchProjects: () => Promise<void>;
  createProject: (name: string) => Promise<void>;
  openProject: (id: string) => Promise<void>;
  saveProject: () => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  setProjectName: (name: string) => void;
  debouncedSave: () => void;
}

export const useProjectStore = create<ProjectState>()((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,
  error: null,
  saveTimeout: null,

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
      set((state) => ({
        projects: [...state.projects, project],
        currentProject: project,
        loading: false,
      }));
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
      set({ currentProject: project, loading: false });
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
      await projectsApi.update(currentProject.id, currentProject);
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
}));
