import { Injectable, signal } from '@angular/core';

export interface WebSocketEventMessage {
  event_type: string;
  sequence_id: number;
  timestamp: string;
  payload: Record<string, any>;
}

@Injectable({
  providedIn: 'root',
})
export class EventSocketService {
  readonly isConnected = signal<boolean>(false);
  readonly recentEvents = signal<WebSocketEventMessage[]>([]);
  private socket: WebSocket | null = null;

  connect(token: string): void {
    if (!token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(token)}`;

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.isConnected.set(true);
      };

      this.socket.onmessage = (event) => {
        try {
          const msg: WebSocketEventMessage = JSON.parse(event.data);
          this.recentEvents.update((events) => [msg, ...events].slice(0, 50));
        } catch (e) {
          console.error('Failed to parse WebSocket event', e);
        }
      };

      this.socket.onclose = () => {
        this.isConnected.set(false);
        setTimeout(() => this.connect(token), 3000);
      };

      this.socket.onerror = () => {
        this.socket?.close();
      };
    } catch (e) {
      console.error('WebSocket connection error', e);
    }
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
      this.isConnected.set(false);
    }
  }
}
