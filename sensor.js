// ============================================
// MY REFRIGERATOR - IoT Sensor Manager
// بيجيب البيانات من الباك إند فقط (لا simulation)
// الباك إند هو اللي بيتكلم مع ESP32 عبر MQTT
// ============================================

class SensorManager {
  constructor() {
    this.connected = false;
    this.onDataCallback = null;
    this.pollInterval = null;
    this.data = {
      temperature: null,
      humidity: null,
      connected: false,
      lastUpdate: null,
      mode: 'disconnected'
    };
  }

  // بيجيب البيانات من الباك إند كل 5 ثواني
  connect() {
    this._fetchFromBackend();
    this.pollInterval = setInterval(() => {
      this._fetchFromBackend();
    }, 5000);
  }

  disconnect() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.connected = false;
    this.data.connected = false;
    this._notifyChange();
  }

  async _fetchFromBackend() {
    try {
      const res  = await apiFetch('/sensor/summary');
      if (!res || !res.success) return;

      const d = res.data;
      this.data.temperature = d.temperature;
      this.data.humidity    = d.humidity;
      this.data.connected   = d.connected;
      this.data.lastUpdate  = d.updated_at;
      this.data.mode        = d.mode || 'disconnected';
      this.connected        = d.connected;

      this._notifyChange();
    } catch (e) {
      console.warn('Sensor fetch failed:', e);
    }
  }

  getData() {
    return { ...this.data };
  }

  onData(callback) {
    this.onDataCallback = callback;
  }

  _notifyChange() {
    if (this.onDataCallback) {
      this.onDataCallback({ ...this.data });
    }
  }

  getStatusLabel() {
    if (!this.data.connected) return 'Offline';
    return 'Live';
  }

  getTempStatus() {
    const t = this.data.temperature;
    if (t === null || t === undefined) return { label: '--', color: '#9ca3af' };
    if (t < 0)  return { label: 'Too Cold',   color: '#3b82f6' };
    if (t <= 4) return { label: 'Optimal',    color: '#10b981' };
    if (t <= 8) return { label: 'Acceptable', color: '#f59e0b' };
    return       { label: 'Too Warm',         color: '#ef4444' };
  }
}

// Global instance
const sensor = new SensorManager();
