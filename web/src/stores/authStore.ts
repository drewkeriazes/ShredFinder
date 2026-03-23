import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types';
import { authApi } from '../services/api';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  error: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      error: null,
      loading: false,

      login: async (username, password) => {
        set({ loading: true, error: null });
        try {
          const res = await authApi.login(username, password);
          set({
            token: res.token,
            user: res.user,
            isAuthenticated: true,
            loading: false,
          });
        } catch (err) {
          set({
            error: err instanceof Error ? err.message : 'Login failed',
            loading: false,
          });
        }
      },

      register: async (username, email, password) => {
        set({ loading: true, error: null });
        try {
          const res = await authApi.register(username, email, password);
          set({
            token: res.token,
            user: res.user,
            isAuthenticated: true,
            loading: false,
          });
        } catch (err) {
          set({
            error: err instanceof Error ? err.message : 'Registration failed',
            loading: false,
          });
        }
      },

      logout: () => {
        set({ token: null, user: null, isAuthenticated: false });
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
