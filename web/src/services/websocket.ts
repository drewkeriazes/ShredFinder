type EventType = 'detection_progress' | 'render_progress' | 'upload_progress';

interface WSMessage {
  type: EventType;
  payload: Record<string, unknown>;
}

type Handler = (payload: Record<string, unknown>) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers = new Map<EventType, Set<Handler>>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  constructor() {
    const base = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
    this.url = `${base}/ws`;
  }

  connect(token?: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const url = token ? `${this.url}?token=${token}` : this.url;
    this.intentionalClose = false;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        console.log('[WS] Connected');
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          const listeners = this.handlers.get(msg.type);
          if (listeners) {
            listeners.forEach((handler) => handler(msg.payload));
          }
        } catch {
          console.warn('[WS] Failed to parse message');
        }
      };

      this.ws.onclose = () => {
        if (!this.intentionalClose) {
          this.scheduleReconnect(token);
        }
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      this.scheduleReconnect(token);
    }
  }

  private scheduleReconnect(token?: string): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WS] Max reconnect attempts reached');
      return;
    }
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connect(token), delay);
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  on(event: EventType, handler: Handler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => {
      this.handlers.get(event)?.delete(handler);
    };
  }
}

export const wsManager = new WebSocketManager();
