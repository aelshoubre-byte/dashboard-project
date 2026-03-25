# ============================================
# mqtt_manager.py
# My Refrigerator IoT Tracker
# ============================================
# بيستقبل بيانات من ESP32 عبر MQTT فقط
# لو مفيش اتصال — بيرجع null مش أرقام وهمية
# ============================================

import json
import random
import threading
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False
    print("⚠️  paho-mqtt not installed. Run: pip install paho-mqtt")


class MQTTManager:
    def __init__(self):
        self.mode      = "disconnected"
        self.on_data   = None
        self.client    = None
        self._lock     = threading.Lock()

        self._temperature = None
        self._humidity    = None
        self._connected   = False
        self._last_update = None

        self.broker = "broker.emqx.io"
        self.port   = 1883
        self.topic  = "fridge/sensor"

    def start(self):
        if PAHO_AVAILABLE:
            self._connect_mqtt()
        else:
            print("❌ paho-mqtt not installed — sensor disabled")

    def _connect_mqtt(self):
        try:
            self.client = mqtt.Client(
                client_id="fridge_server_" + str(random.randint(1000, 9999))
            )
            self.client.on_connect    = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message    = self._on_message

            def connect_thread():
                try:
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_forever()
                except Exception as e:
                    print(f"⚠️  MQTT connection failed: {e}")
                    self._connected = False
                    self.mode = "disconnected"

            t = threading.Thread(target=connect_thread, daemon=True)
            t.start()
        except Exception as e:
            print(f"⚠️  MQTT setup failed: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            # متوصل بالـ broker بس مش بالـ ESP32 بعد
            # connected يفضل False لحد ما تيجي message حقيقية من ESP32
            self.mode       = "broker_only"
            self._connected = False
            client.subscribe(self.topic)
            print(f"✅ MQTT broker connected → {self.broker} | waiting for ESP32 data...")
        else:
            print(f"⚠️  MQTT connect error rc={rc}")
            self.mode       = "disconnected"
            self._connected = False

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        self.mode       = "disconnected"
        print("⚠️  MQTT disconnected")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            temp    = float(payload.get("temperature"))
            hum     = float(payload.get("humidity"))

            with self._lock:
                self._temperature = round(temp, 1)
                self._humidity    = round(hum,  1)
                self._connected   = True
                self._last_update = datetime.now().isoformat()
                self.mode         = "mqtt"

            if self.on_data:
                self.on_data(self._temperature, self._humidity, True, "mqtt")

        except Exception as e:
            print(f"⚠️  MQTT message error: {e}")

    def get_data(self):
        with self._lock:
            return {
                "temperature": self._temperature,
                "humidity":    self._humidity,
                "connected":   self._connected,
                "mode":        self.mode,
                "updated_at":  self._last_update,
            }

    def reconfigure(self, broker=None, port=None, topic=None):
        if broker: self.broker = broker
        if port:   self.port   = int(port)
        if topic:  self.topic  = topic
        print(f"🔧 Reconfiguring → {self.broker}:{self.port} / {self.topic}")
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None
        self.mode       = "disconnected"
        self._connected = False
        if PAHO_AVAILABLE:
            self._connect_mqtt()


mqtt_manager = MQTTManager()
