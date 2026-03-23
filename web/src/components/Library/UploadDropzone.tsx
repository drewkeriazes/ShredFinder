import { useState, useRef, useCallback } from 'react';
import { Upload } from 'lucide-react';
import { useMediaStore } from '../../stores/mediaStore';

export function UploadDropzone() {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadFile = useMediaStore((s) => s.uploadFile);
  const uploadProgress = useMediaStore((s) => s.uploadProgress);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      Array.from(files).forEach((file) => {
        if (file.name.toLowerCase().endsWith('.mp4')) {
          uploadFile(file);
        }
      });
    },
    [uploadFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const progressEntries = Object.entries(uploadProgress);

  return (
    <div className="px-3 pb-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-4 transition ${
          dragging
            ? 'border-blue-500 bg-blue-500/10'
            : 'border-zinc-600 hover:border-zinc-500 hover:bg-zinc-800'
        }`}
      >
        <Upload className="mb-1 h-5 w-5 text-zinc-500" />
        <p className="text-xs text-zinc-400">
          Drop .mp4 files here or{' '}
          <span className="text-blue-400">browse</span>
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".mp4,.MP4"
          multiple
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {progressEntries.length > 0 && (
        <div className="mt-2 space-y-1">
          {progressEntries.map(([id, pct]) => (
            <div key={id} className="flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-700">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-[10px] text-zinc-500">{pct}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
