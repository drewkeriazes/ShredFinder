import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Mountain,
  Undo2,
  Redo2,
  Download,
  ChevronDown,
  LogOut,
  Save,
  Loader2,
} from 'lucide-react';
import { useTimelineStore } from '../../stores/timelineStore';
import { useProjectStore } from '../../stores/projectStore';
import { useAuthStore } from '../../stores/authStore';
import { renderApi } from '../../services/api';

export function Toolbar() {
  const undo = useTimelineStore((s) => s.undo);
  const redo = useTimelineStore((s) => s.redo);
  const historyIndex = useTimelineStore((s) => s.historyIndex);
  const historyLength = useTimelineStore((s) => s.history.length);
  const currentProject = useProjectStore((s) => s.currentProject);
  const setProjectName = useProjectStore((s) => s.setProjectName);
  const saveProject = useProjectStore((s) => s.saveProject);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState('');
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleExport = useCallback(async () => {
    if (!currentProject) {
      alert('No project open. Create or open a project first.');
      return;
    }
    setExporting(true);
    try {
      const job = await renderApi.submit(currentProject.id);
      // Poll for render completion
      const poll = async (): Promise<void> => {
        const status = await renderApi.status(job.id);
        if (status.status === 'done') {
          window.open(renderApi.downloadUrl(job.id), '_blank');
          return;
        }
        if (status.status === 'error') {
          alert(`Export failed: ${status.error || 'Unknown error'}`);
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
        return poll();
      };
      await poll();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  }, [currentProject]);

  useEffect(() => {
    if (editingName && nameInputRef.current) {
      nameInputRef.current.focus();
      nameInputRef.current.select();
    }
  }, [editingName]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleNameSubmit = () => {
    if (nameValue.trim()) {
      setProjectName(nameValue.trim());
    }
    setEditingName(false);
  };

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-700 bg-zinc-800 px-4">
      {/* Logo */}
      <div className="flex items-center gap-2 text-blue-500">
        <Mountain className="h-5 w-5" />
        <span className="text-sm font-bold text-zinc-100">ShredFinder</span>
      </div>

      <div className="mx-4 h-6 w-px bg-zinc-700" />

      {/* Project Name */}
      {editingName ? (
        <input
          ref={nameInputRef}
          value={nameValue}
          onChange={(e) => setNameValue(e.target.value)}
          onBlur={handleNameSubmit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleNameSubmit();
            if (e.key === 'Escape') setEditingName(false);
          }}
          className="rounded bg-zinc-700 px-2 py-1 text-sm text-zinc-100 outline-none focus:ring-1 focus:ring-blue-500"
        />
      ) : (
        <button
          onClick={() => {
            setNameValue(currentProject?.name || 'Untitled Project');
            setEditingName(true);
          }}
          className="rounded px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
        >
          {currentProject?.name || 'Untitled Project'}
        </button>
      )}

      {/* Save */}
      <button
        onClick={() => saveProject()}
        className="rounded p-1.5 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
        title="Save (Ctrl+S)"
      >
        <Save className="h-4 w-4" />
      </button>

      <div className="flex-1" />

      {/* Undo / Redo */}
      <button
        onClick={undo}
        disabled={historyIndex < 0}
        className="rounded p-1.5 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="Undo (Ctrl+Z)"
      >
        <Undo2 className="h-4 w-4" />
      </button>
      <button
        onClick={redo}
        disabled={historyIndex >= historyLength - 1}
        className="rounded p-1.5 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="Redo (Ctrl+Y)"
      >
        <Redo2 className="h-4 w-4" />
      </button>

      <div className="mx-2 h-6 w-px bg-zinc-700" />

      {/* Render */}
      <button
        onClick={handleExport}
        disabled={exporting}
        className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-500 disabled:opacity-60"
      >
        {exporting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        {exporting ? 'Exporting...' : 'Export'}
      </button>

      <div className="mx-2 h-6 w-px bg-zinc-700" />

      {/* User Menu */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          className="flex items-center gap-1.5 rounded px-2 py-1 text-sm text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-600 text-xs font-medium text-zinc-200">
            {user?.username?.charAt(0).toUpperCase() || '?'}
          </div>
          <ChevronDown className="h-3 w-3" />
        </button>

        {userMenuOpen && (
          <div className="absolute right-0 top-full mt-1 w-48 rounded-lg border border-zinc-700 bg-zinc-800 py-1 shadow-xl">
            <div className="border-b border-zinc-700 px-3 py-2">
              <p className="text-sm font-medium text-zinc-200">{user?.username}</p>
              <p className="text-xs text-zinc-500">{user?.email}</p>
            </div>
            <button
              onClick={() => {
                setUserMenuOpen(false);
                logout();
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
