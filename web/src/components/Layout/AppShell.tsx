import {
  Group,
  Panel,
  Separator,
} from 'react-resizable-panels';
import { Toolbar } from './Toolbar';
import { ClipLibrary } from '../Library/ClipLibrary';
import { PreviewPlayer } from '../Preview/PreviewPlayer';
import { Timeline } from '../Timeline/Timeline';
import { InspectorPanel } from '../Inspector/InspectorPanel';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';

export function AppShell() {
  useKeyboardShortcuts();

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-zinc-900">
      <Toolbar />

      <Group orientation="vertical" className="flex-1">
        {/* Top half: Library | Preview | Inspector */}
        <Panel defaultSize={55} minSize={30}>
          <Group orientation="horizontal">
            {/* Clip Library */}
            <Panel defaultSize={30} minSize={15}>
              <div className="h-full overflow-hidden border-r border-zinc-700">
                <ClipLibrary />
              </div>
            </Panel>

            <Separator className="w-1 bg-zinc-700 hover:bg-blue-500 transition-colors" />

            {/* Preview Player */}
            <Panel defaultSize={45} minSize={20}>
              <div className="h-full overflow-hidden border-r border-zinc-700">
                <PreviewPlayer />
              </div>
            </Panel>

            <Separator className="w-1 bg-zinc-700 hover:bg-blue-500 transition-colors" />

            {/* Inspector */}
            <Panel defaultSize={25} minSize={15} collapsible>
              <div className="h-full overflow-hidden">
                <InspectorPanel />
              </div>
            </Panel>
          </Group>
        </Panel>

        <Separator className="h-1 bg-zinc-700 hover:bg-blue-500 transition-colors" />

        {/* Bottom: Timeline */}
        <Panel defaultSize={45} minSize={20}>
          <div className="h-full overflow-hidden">
            <Timeline />
          </div>
        </Panel>
      </Group>
    </div>
  );
}
