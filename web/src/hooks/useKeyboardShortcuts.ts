import { useEffect } from 'react';
import { useTimelineStore } from '../stores/timelineStore';
import { useProjectStore } from '../stores/projectStore';

export function useKeyboardShortcuts(): void {
  const togglePlay = useTimelineStore((s) => s.togglePlay);
  const pause = useTimelineStore((s) => s.pause);
  const setPlayhead = useTimelineStore((s) => s.setPlayhead);
  const removeClip = useTimelineStore((s) => s.removeClip);
  const undo = useTimelineStore((s) => s.undo);
  const redo = useTimelineStore((s) => s.redo);
  const saveProject = useProjectStore((s) => s.saveProject);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      const ctrl = e.ctrlKey || e.metaKey;

      switch (e.key) {
        case ' ':
          e.preventDefault();
          togglePlay();
          break;

        case 'k':
        case 'K':
          e.preventDefault();
          pause();
          break;

        case 'j':
        case 'J':
          e.preventDefault();
          setPlayhead(useTimelineStore.getState().playheadPosition - 5);
          break;

        case 'l':
        case 'L':
          e.preventDefault();
          setPlayhead(useTimelineStore.getState().playheadPosition + 5);
          break;

        case 'ArrowLeft':
          e.preventDefault();
          setPlayhead(useTimelineStore.getState().playheadPosition - (1 / 30));
          break;

        case 'ArrowRight':
          e.preventDefault();
          setPlayhead(useTimelineStore.getState().playheadPosition + (1 / 30));
          break;

        case 'Delete':
        case 'Backspace': {
          const selected = useTimelineStore.getState().selectedClipId;
          if (selected) {
            e.preventDefault();
            removeClip(selected);
          }
          break;
        }

        case 'z':
        case 'Z':
          if (ctrl) {
            e.preventDefault();
            if (e.shiftKey) {
              redo();
            } else {
              undo();
            }
          }
          break;

        case 'y':
        case 'Y':
          if (ctrl) {
            e.preventDefault();
            redo();
          }
          break;

        case 's':
        case 'S':
          if (ctrl) {
            e.preventDefault();
            saveProject();
          }
          break;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [togglePlay, pause, setPlayhead, removeClip, undo, redo, saveProject]);
}
