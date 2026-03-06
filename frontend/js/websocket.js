/**
 * F1 Dashboard WebSocket Client
 * Auto-reconnecting WebSocket with state callback.
 */
class F1Socket {
  constructor(channel, onState) {
    this.channel = channel;
    this.onState = onState;
    this.ws = null;
    this.reconnectDelay = 2000;
    this.connect();
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}/ws/${this.channel}`);

    this.ws.onopen = () => {
      console.log(`[F1] Connected to ${this.channel}`);
      this.reconnectDelay = 2000;
    };

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "keepalive" || data.type === "pong") return;
        if (data.type === "refresh") { location.reload(); return; }
        this.onState(data);
      } catch (err) {
        console.warn("[F1] Parse error:", err);
      }
    };

    this.ws.onclose = () => {
      console.log(`[F1] Disconnected from ${this.channel}, reconnecting in ${this.reconnectDelay}ms...`);
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 10000);
    };

    this.ws.onerror = () => {}; // onclose handles reconnection
  }
}
