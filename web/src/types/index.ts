export interface User {
  id: string;
  username: string;
  email: string;
}

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  timeline: TimelineState;
}

export interface MediaFile {
  id: string;
  filename: string;
  duration: number;
  width: number;
  height: number;
  thumbnailUrl: string;
  proxyUrl: string;
  status: 'uploading' | 'processing' | 'ready' | 'error';
  clips: DetectedClip[];
}

export interface DetectedClip {
  id: string;
  type: 'jump' | 'spin' | 'speed' | 'crash';
  startTime: number;
  endTime: number;
  confidence: number;
  metadata: ClipMetadata;
}

export interface ClipMetadata {
  airtime?: number;
  speed?: number;
  rotation?: number;
  landingQuality?: 'clean' | 'sketchy' | 'crash';
  label?: string;
}

export interface Track {
  id: string;
  name: string;
  type: 'video' | 'audio';
  clips: TimelineClip[];
  muted: boolean;
  locked: boolean;
  visible: boolean;
}

export interface TimelineClip {
  id: string;
  mediaId: string;
  trackId: string;
  startTime: number;
  duration: number;
  trimStart: number;
  trimEnd: number;
  name: string;
  type: 'jump' | 'spin' | 'speed' | 'crash' | 'custom';
  metadata?: ClipMetadata;
  speed?: number;
  volume?: number;
  opacity?: number;
}

export interface TimelineState {
  tracks: Track[];
  playheadPosition: number;
  zoom: number;
  scrollPosition: number;
}

export interface RenderJob {
  id: string;
  projectId: string;
  status: 'queued' | 'rendering' | 'done' | 'error';
  progress: number;
  outputUrl?: string;
  error?: string;
}

export interface DetectionResult {
  mediaId: string;
  status: 'queued' | 'running' | 'done' | 'error';
  progress: number;
  clips: DetectedClip[];
}

export interface ApiResponse<T> {
  data: T;
  error?: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}
