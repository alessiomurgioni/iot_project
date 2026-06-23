#include <SoftwareSerial.h>
#include <DHT.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

// ══════════════════════════════════════════════════════════════════════════════
//  WiFi & CoAP configuration  –  EDIT THESE THREE LINES
// ══════════════════════════════════════════════════════════════════════════════
const char* WIFI_SSID     = "iPhone di Alessio";   // iPhone hotspot SSID
const char* WIFI_PASSWORD = "alessio2";     // iPhone hotspot password
const char* SERVER_IP     = "172.20.10.12";             // IP printed by the Python server
// ══════════════════════════════════════════════════════════════════════════════

// CoAP constants
const uint16_t COAP_PORT      = 5683;
const uint16_t LOCAL_UDP_PORT = 5684;   // local port for UDP replies

// CoAP message types / codes
const uint8_t COAP_CON     = 0x40;  // Confirmable
const uint8_t COAP_GET     = 0x01;
const uint8_t COAP_ACK     = 0x60;

// Timing
const unsigned long COAP_INTERVAL_MS  = 15000UL;  // poll server every 15 s
const unsigned long COAP_TIMEOUT_MS   =  5000UL;  // wait up to 5 s for response
const unsigned long WIFI_RETRY_MS     =  5000UL;  // retry WiFi every 5 s

// ── DHT11 ─────────────────────────────────────────────────────────────────────
#define DHTPIN    D4
#define DHTTYPE   DHT11

// ── SoftwareSerial link to Arduino ────────────────────────────────────────────
#define NODE_RX   D5   // receives from Arduino TX
#define NODE_TX   D6   // sends to Arduino RX

// ── IR Flame sensor ───────────────────────────────────────────────────────────
#define IR_FLAME_PIN  D1

// ── People counter – IR obstacle-avoidance sensors (LM393) ───────────────────
const uint8_t SENSOR_1_PIN = D0;   // outside sensor
const uint8_t SENSOR_2_PIN = D2;   // inside  sensor

const uint8_t DETECTED_LEVEL = LOW;

// Timing settings
const unsigned long DEBOUNCE_TIME_MS    =   35;
const unsigned long PASSAGE_TIMEOUT_MS  = 1200;
const unsigned long REARM_TIME_MS       =  250;

DHT dht(DHTPIN, DHTTYPE);
SoftwareSerial linkSerial(NODE_RX, NODE_TX);
WiFiUDP udp;

// ── People-counter variables ───────────────────────────────────────────────────
int  peopleInside  = 0;
unsigned long totalEntries = 0;
unsigned long totalExits   = 0;

// ── External temperature (from CoAP server) ───────────────────────────────────
float externalTemperature = NAN;
unsigned long lastCoapRequest = 0;

// ── CoAP message ID ───────────────────────────────────────────────────────────
uint16_t coapMsgId = 1;


// ── Sensor debouncing ─────────────────────────────────────────────────────────
struct SensorFilter {
  bool rawState;
  bool stableState;
  unsigned long lastChangeTime;
};

SensorFilter sensor1Filter;
SensorFilter sensor2Filter;


// ── Counter state machine ─────────────────────────────────────────────────────
enum CounterState {
  IDLE,
  SENSOR_1_TRIGGERED_FIRST,
  SENSOR_2_TRIGGERED_FIRST,
  WAIT_FOR_CLEAR
};

CounterState currentState = IDLE;

unsigned long sequenceStartTime = 0;
unsigned long clearStartTime    = 0;


// ── WiFi helpers ──────────────────────────────────────────────────────────────

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("[WiFi] Connecting to ");
  Serial.print(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000UL) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("[WiFi] Connected! NodeMCU IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("[WiFi] Connection failed. Will retry later.");
  }
}


// ── Minimal CoAP GET builder ──────────────────────────────────────────────────
//
// CoAP packet layout (RFC 7252):
//   Byte 0    : Ver(2b)=01 | T(2b) | TKL(4b)
//   Byte 1    : Code
//   Bytes 2-3 : Message ID
//   Bytes 4.. : Token (TKL bytes)
//   Then options, then payload
//
// Resource: /sensor/temperature
//   Option 11 (Uri-Path) "sensor"       delta=11, len=6
//   Option 11 (Uri-Path) "temperature"  delta= 0, len=11
//
int buildCoapGet(uint8_t* buf, uint16_t msgId) {
  int idx = 0;

  // Header: Ver=1, Type=CON(0), TKL=0
  buf[idx++] = 0x40;
  buf[idx++] = COAP_GET;
  buf[idx++] = (msgId >> 8) & 0xFF;
  buf[idx++] = msgId & 0xFF;

  // Option 11 (Uri-Path) = "sensor"  (delta=11, len=6)
  buf[idx++] = 0xB6;  // delta=11, len=6
  memcpy(&buf[idx], "sensor", 6); idx += 6;

  // Option 11 (Uri-Path) = "temperature"  (delta=0, len=11)
  buf[idx++] = 0x0B;  // delta=0, len=11
  memcpy(&buf[idx], "temperature", 11); idx += 11;

  return idx;
}


// ── Send CoAP GET and wait for the response ───────────────────────────────────
//
// Sends one UDP datagram to SERVER_IP:5683 and blocks for up to
// COAP_TIMEOUT_MS waiting for a reply. On success the payload is
// parsed as a float and stored in externalTemperature.
//
void requestExternalTemperature() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[CoAP] WiFi not connected – skipping request");
    return;
  }

  uint8_t packet[64];
  int len = buildCoapGet(packet, coapMsgId++);

  udp.beginPacket(SERVER_IP, COAP_PORT);
  udp.write(packet, len);
  udp.endPacket();

  Serial.print("[CoAP] GET coap://");
  Serial.print(SERVER_IP);
  Serial.println(":5683/sensor/temperature");

  // Wait for ACK / response
  unsigned long start = millis();
  while (millis() - start < COAP_TIMEOUT_MS) {
    int pktSize = udp.parsePacket();
    if (pktSize > 0) {
      uint8_t reply[128];
      int n = udp.read(reply, sizeof(reply));

      if (n < 4) break;  // malformed

      uint8_t code = reply[1];
      // 2.05 Content = 0x45
      if (code == 0x45 && n > 4) {
        // Skip header (4 bytes) + token (TKL bytes) + options
        // The server sends no token and no options, so payload starts at byte 4.
        // Find the payload marker 0xFF if present.
        int payloadStart = 4;
        for (int i = 4; i < n; i++) {
          if (reply[i] == 0xFF) { payloadStart = i + 1; break; }
        }

        char payloadStr[32] = {0};
        int payloadLen = n - payloadStart;
        if (payloadLen > 0 && payloadLen < (int)sizeof(payloadStr)) {
          memcpy(payloadStr, &reply[payloadStart], payloadLen);
          externalTemperature = atof(payloadStr);
          Serial.print("[CoAP] External temperature: ");
          Serial.print(externalTemperature, 1);
          Serial.println(" °C");
        }
      } else {
        // Print raw payload for debugging
        Serial.print("[CoAP] Response code: 0x");
        Serial.println(code, HEX);
      }
      break;
    }
    delay(10);
  }

  if (millis() - start >= COAP_TIMEOUT_MS) {
    Serial.println("[CoAP] Timeout – no response from server");
  }
}


// ── Sensor helpers ────────────────────────────────────────────────────────────

bool readDebouncedSensor(SensorFilter &filter, uint8_t pin) {
  bool currentRawState = (digitalRead(pin) == DETECTED_LEVEL);
  unsigned long currentTime = millis();

  if (currentRawState != filter.rawState) {
    filter.rawState = currentRawState;
    filter.lastChangeTime = currentTime;
  }

  if (filter.stableState != filter.rawState &&
      currentTime - filter.lastChangeTime >= DEBOUNCE_TIME_MS) {
    filter.stableState = filter.rawState;
  }

  return filter.stableState;
}

void initializeSensorFilter(SensorFilter &filter, uint8_t pin) {
  bool detected = (digitalRead(pin) == DETECTED_LEVEL);
  filter.rawState       = detected;
  filter.stableState    = detected;
  filter.lastChangeTime = millis();
}


// ── Counter event handlers ────────────────────────────────────────────────────

void sendPeopleInsideFlag() {
  if (peopleInside > 0) {
    linkSerial.println("PEOPLE_INSIDE:1");
    Serial.println("    [flag] PEOPLE_INSIDE:1 sent to actuator");
  } else {
    linkSerial.println("PEOPLE_INSIDE:0");
    Serial.println("    [flag] PEOPLE_INSIDE:0 sent to actuator");
  }
}

void registerEntry() {
  totalEntries++;
  peopleInside++;

  Serial.println(">>> ENTRY detected");
  Serial.print("    Entries: ");    Serial.print(totalEntries);
  Serial.print(" | Exits: ");       Serial.print(totalExits);
  Serial.print(" | People inside: "); Serial.println(peopleInside);

  sendPeopleInsideFlag();

  currentState   = WAIT_FOR_CLEAR;
  clearStartTime = 0;
}

void registerExit() {
  totalExits++;
  if (peopleInside > 0) peopleInside--;

  Serial.println("<<< EXIT detected");
  Serial.print("    Entries: ");    Serial.print(totalEntries);
  Serial.print(" | Exits: ");       Serial.print(totalExits);
  Serial.print(" | People inside: "); Serial.println(peopleInside);

  sendPeopleInsideFlag();

  currentState   = WAIT_FOR_CLEAR;
  clearStartTime = 0;
}


// ── People counter – runs every loop iteration (non-blocking) ─────────────────
void updatePeopleCounter() {
  bool sensor1Detected = readDebouncedSensor(sensor1Filter, SENSOR_1_PIN);
  bool sensor2Detected = readDebouncedSensor(sensor2Filter, SENSOR_2_PIN);

  unsigned long currentTime = millis();

  switch (currentState) {

    case IDLE:
      if (sensor1Detected && sensor2Detected) {
        currentState   = WAIT_FOR_CLEAR;
        clearStartTime = 0;
      } else if (sensor1Detected) {
        currentState      = SENSOR_1_TRIGGERED_FIRST;
        sequenceStartTime = currentTime;
      } else if (sensor2Detected) {
        currentState      = SENSOR_2_TRIGGERED_FIRST;
        sequenceStartTime = currentTime;
      }
      break;

    case SENSOR_1_TRIGGERED_FIRST:
      if (sensor2Detected) {
        registerEntry();
      } else if (currentTime - sequenceStartTime > PASSAGE_TIMEOUT_MS) {
        currentState = (sensor1Detected || sensor2Detected) ? WAIT_FOR_CLEAR : IDLE;
      }
      break;

    case SENSOR_2_TRIGGERED_FIRST:
      if (sensor1Detected) {
        registerExit();
      } else if (currentTime - sequenceStartTime > PASSAGE_TIMEOUT_MS) {
        currentState = (sensor1Detected || sensor2Detected) ? WAIT_FOR_CLEAR : IDLE;
      }
      break;

    case WAIT_FOR_CLEAR:
      if (!sensor1Detected && !sensor2Detected) {
        if (clearStartTime == 0) clearStartTime = currentTime;
        if (currentTime - clearStartTime >= REARM_TIME_MS) {
          currentState   = IDLE;
          clearStartTime = 0;
        }
      } else {
        clearStartTime = 0;
      }
      break;
  }
}


// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  linkSerial.begin(9600);
  dht.begin();

  pinMode(IR_FLAME_PIN, INPUT);
  pinMode(SENSOR_1_PIN, INPUT);
  pinMode(SENSOR_2_PIN, INPUT);

  initializeSensorFilter(sensor1Filter, SENSOR_1_PIN);
  initializeSensorFilter(sensor2Filter, SENSOR_2_PIN);

  // Connect to iPhone hotspot
  connectWiFi();

  // Open local UDP socket for CoAP
  udp.begin(LOCAL_UDP_PORT);

  // First CoAP request immediately after boot
  requestExternalTemperature();
  lastCoapRequest = millis();

  Serial.println("NodeMCU ready");
  Serial.println("Person counter started – inside: 0");
}


// ─────────────────────────────────────────────────────────────────────────────
void loop() {

  // ── 0. Reconnect WiFi if dropped ──────────────────────────────────────────
  static unsigned long lastWifiCheck = 0;
  if (millis() - lastWifiCheck > WIFI_RETRY_MS) {
    lastWifiCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] Connection lost – reconnecting...");
      connectWiFi();
    }
  }

  // ── 1. CoAP request every 15 seconds ──────────────────────────────────────
  if (millis() - lastCoapRequest >= COAP_INTERVAL_MS) {
    lastCoapRequest = millis();
    requestExternalTemperature();

    // Print external temperature summary
    if (!isnan(externalTemperature)) {
      Serial.print("[EXT TEMP] Current outdoor temperature in Cagliari: ");
      Serial.print(externalTemperature, 1);
      Serial.println(" °C");
    }
  }

  // ── 2. People counter (non-blocking, runs every iteration) ────────────────
  updatePeopleCounter();

  // ── 3. DHT11 local temperature read ───────────────────────────────────────
  float temp = dht.readTemperature();

  if (isnan(temp)) {
    Serial.println("Failed to read from DHT11");
    delay(2000);
    return;
  }

  char signalToSend = (temp > 25.0) ? '1' : '2';

  linkSerial.println(signalToSend);

  Serial.print("[DHT11]   Indoor temperature: ");
  Serial.print(temp);
  Serial.print(" °C | Sent to Arduino: ");
  Serial.println(signalToSend);

  // ── 4. Wait for ACK from Arduino ──────────────────────────────────────────
  unsigned long startTime = millis();
  String ack = "";

  while (millis() - startTime < 1000) {
    updatePeopleCounter();
    if (linkSerial.available()) {
      ack = linkSerial.readStringUntil('\n');
      ack.trim();
      break;
    }
  }

  if (ack.length() > 0) {
    Serial.print("Received from Arduino: ");
    Serial.println(ack);
  } else {
    Serial.println("No ACK received");
  }

  // ── 5. IR Flame sensor check ───────────────────────────────────────────────
  bool fireDetected = (digitalRead(IR_FLAME_PIN) == LOW);

  if (fireDetected) {
    Serial.println("FIRE DETECTED! Sending alert to Arduino...");
    linkSerial.println("FIRE");

    unsigned long fireStart = millis();
    String fireAck = "";

    while (millis() - fireStart < 4000) {
      updatePeopleCounter();
      if (linkSerial.available()) {
        fireAck = linkSerial.readStringUntil('\n');
        fireAck.trim();
        break;
      }
    }

    if (fireAck.length() > 0) {
      Serial.print("Arduino fire ACK: ");
      Serial.println(fireAck);
    } else {
      Serial.println("No fire ACK received");
    }
  }

  // ── 6. Short delay (non-blocking) ─────────────────────────────────────────
  unsigned long delayStart = millis();
  while (millis() - delayStart < 2000) {
    updatePeopleCounter();
    delay(10);
  }
}
