// ============================================
// Esp.cpp — ESP32 IoT Sensor
// My Refrigerator Smart Tracker
// ============================================
//
// الجهاز:   ESP32
// السنسور:  DHT11 على Pin 4
// الشاشة:   OLED SSD1306 128x64 (I2C: SDA=21, SCL=22)
// البروتوكول: MQTT عبر WiFi
// الـ Topic:  fridge/sensor
// الـ Payload: {"temperature": 3.5, "humidity": 68.2}
//
// المكتبات المطلوبة (Arduino Library Manager):
//   - DHT sensor library (Adafruit)
//   - Adafruit SSD1306
//   - Adafruit GFX Library
//   - PubSubClient (MQTT)
// ============================================

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <WiFi.h>
#include <PubSubClient.h>

// ─── إعدادات الشاشة ───────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64

// ─── إعدادات السنسور ──────────────────────
#define DHTPIN  4
#define DHTTYPE DHT11

// ─── إعدادات WiFi ─────────────────────────
// *** غيّر الاسم والباسورد لشبكتك ***
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ─── إعدادات MQTT ─────────────────────────
// Broker مجاني للتجربة — نفس اللي في mqtt_manager.py
const char* MQTT_BROKER = "broker.emqx.io";
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "fridge/sensor";
const char* MQTT_CLIENT_ID = "fridge_esp32_001";  // لازم يكون unique

// ─── كل كام ثانية يبعت قراءة ─────────────
const unsigned long SEND_INTERVAL = 5000;  // 5 ثواني

// ─── Objects ──────────────────────────────
DHT                  dht(DHTPIN, DHTTYPE);
Adafruit_SSD1306     display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
WiFiClient           wifiClient;
PubSubClient         mqttClient(wifiClient);

unsigned long lastSendTime = 0;
bool          mqttWasConnected = false;

// ============================================
// SETUP
// ============================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n🚀 My Refrigerator — ESP32 Sensor Starting...");

  // تشغيل السنسور
  dht.begin();

  // تشغيل الشاشة
  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("❌ OLED display not found!");
  } else {
    display.clearDisplay();
    display.setTextColor(WHITE);
    showBootScreen();
  }

  // الاتصال بـ WiFi
  connectWiFi();

  // إعداد MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setKeepAlive(60);
}

// ============================================
// LOOP
// ============================================
void loop() {
  // تأكد إن WiFi متصل
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️  WiFi disconnected — reconnecting...");
    connectWiFi();
  }

  // تأكد إن MQTT متصل
  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  // ابعت قراءة كل SEND_INTERVAL
  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;
    readAndSend();
  }
}

// ============================================
// قراءة السنسور وإرسالها
// ============================================
void readAndSend() {
  float humidity    = dht.readHumidity();
  float temperature = dht.readTemperature();

  // تحقق من صحة القراءة
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("⚠️  DHT11 read failed — check wiring!");
    showErrorScreen("DHT Read Error");
    return;
  }

  // اطبع في Serial للـ debugging
  Serial.printf("📊 Temp: %.1f°C | Humidity: %.1f%%\n", temperature, humidity);

  // اعمل JSON payload
  char payload[64];
  snprintf(payload, sizeof(payload),
    "{\"temperature\":%.1f,\"humidity\":%.1f}",
    temperature, humidity
  );

  // ابعت على MQTT
  if (mqttClient.connected()) {
    bool sent = mqttClient.publish(MQTT_TOPIC, payload);
    if (sent) {
      Serial.printf("✅ MQTT published → %s\n", payload);
    } else {
      Serial.println("❌ MQTT publish failed");
    }
  }

  // اعرض على الشاشة
  showSensorData(temperature, humidity);
}

// ============================================
// الاتصال بـ WiFi
// ============================================
void connectWiFi() {
  Serial.printf("📶 Connecting to WiFi: %s\n", WIFI_SSID);
  showStatusScreen("Connecting WiFi...", WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n✅ WiFi connected! IP: %s\n", WiFi.localIP().toString().c_str());
    showStatusScreen("WiFi Connected!", WiFi.localIP().toString().c_str());
    delay(1500);
  } else {
    Serial.println("\n❌ WiFi failed! Check SSID/Password");
    showErrorScreen("WiFi Failed!");
    delay(3000);
  }
}

// ============================================
// الاتصال بـ MQTT Broker
// ============================================
void connectMQTT() {
  Serial.printf("📡 Connecting to MQTT: %s:%d\n", MQTT_BROKER, MQTT_PORT);
  showStatusScreen("Connecting MQTT...", MQTT_BROKER);

  int attempts = 0;
  while (!mqttClient.connected() && attempts < 5) {
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("✅ MQTT connected!");
      showStatusScreen("MQTT Connected!", MQTT_TOPIC);
      delay(1000);
    } else {
      Serial.printf("⚠️  MQTT failed (rc=%d) — retry %d/5\n", mqttClient.state(), attempts + 1);
      delay(2000);
    }
    attempts++;
  }

  if (!mqttClient.connected()) {
    Serial.println("❌ MQTT connection failed after 5 attempts");
    showErrorScreen("MQTT Failed!");
  }
}

// ============================================
// عرض البيانات على الشاشة
// ============================================
void showSensorData(float temp, float hum) {
  display.clearDisplay();

  // عنوان
  display.setTextSize(1);
  display.setCursor(10, 0);
  display.print("My Refrigerator");

  // خط فاصل
  display.drawLine(0, 10, 127, 10, WHITE);

  // درجة الحرارة — كبير
  display.setTextSize(2);
  display.setCursor(0, 16);
  display.print("T:");
  display.print(temp, 1);
  display.print("C");

  // الرطوبة — كبير
  display.setCursor(0, 38);
  display.print("H:");
  display.print(hum, 1);
  display.print("%");

  // حالة الاتصال
  display.setTextSize(1);
  display.setCursor(0, 57);
  if (mqttClient.connected()) {
    display.print("MQTT: OK");
  } else {
    display.print("MQTT: --");
  }

  // IP
  display.setCursor(60, 57);
  display.print(WiFi.localIP().toString().substring(9)); // آخر أرقام الـ IP

  display.display();
}

void showBootScreen() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(15, 10);
  display.print("My Refrigerator");
  display.setCursor(25, 25);
  display.print("IoT Tracker");
  display.setCursor(30, 42);
  display.print("Starting...");
  display.display();
  delay(2000);
}

void showStatusScreen(const char* line1, const char* line2) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 15);
  display.print(line1);
  display.setCursor(0, 35);
  display.print(line2);
  display.display();
}

void showErrorScreen(const char* msg) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(30, 10);
  display.print("ERROR!");
  display.drawRect(0, 0, 128, 64, WHITE);
  display.setCursor(5, 35);
  display.print(msg);
  display.display();
}
