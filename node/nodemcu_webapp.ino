#include <SoftwareSerial.h>
#include <DHT.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiUdp.h>
#include <WiFiClient.h>

// ══════════════════════════════════════════════════════════════════════════════
//  WiFi & CoAP configuration  –  EDIT THESE THREE LINES
// ══════════════════════════════════════════════════════════════════════════════
const char* WIFI_SSID     = "iPhone di Riccardo";   // iPhone hotspot SSID
const char* WIFI_PASSWORD = "riccardo";     // iPhone hotspot password
const char* SERVER_IP     = "172.20.10.2";             // IP printed by the Python server
// ══════════════════════════════════════════════════════════════════════════════

const uint16_t SERVER_PORT = 8000;                   // must match config.PORT

// Must match config.DEVICE_TOKEN_HASH on the server (the server only stores a
// hash of this; this is the same value flashed here and printed on the device).
const char* DEVICE_TOKEN  = "node-secret-123";
// ══════════════════════════════════════════════════════════════════════════════

// Timing
const unsigned long OUTDOOR_POLL_MS = 15000UL;  // refresh outdoor temp every 15 s
const unsigned long REPORT_INTERVAL_MS = 2000UL; // matches the old loop cadence
const unsigned long HTTP_TIMEOUT_MS  =  5000UL;
const unsigned long WIFI_RETRY_MS    =  5000UL;

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

// ── People-counter variables ───────────────────────────────────────────────────
int  peopleInside  = 0;
unsigned long totalEntries = 0;
unsigned long totalExits   = 0;

// ── External temperature (pulled from the webapp) ──────────────────────────────
float externalTemperature = NAN;
unsigned long lastOutdoorPoll = 0;

// ── Owner's desired AC behaviour (pulled from the webapp) ─────────────────────
// mode: "auto" | "cool" | "heat" | "off"
String acMode      = "auto";
float  acThreshold  = 25.0;

// ── Window state held on the NodeMCU ──────────────────────────────────────────
// Two variables, as required:
//   windowCommand     -> what the server wants ("open" | "close" | "none")
//   lastWindowCommand -> the last command we actually pushed to the Arduino
// Plus windowsOpen, the ACTUAL state (confirmed by the Arduino ACK), which we
// report back to the server so its _state["windows"] stays in sync.
String windowCommand     = "none";
String lastWindowCommand = "none";
bool   windowsOpen       = false;   // false = closed, true = open


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


// ── Small JSON value extractor ─────────────────────────────────────────────────
// Minimal helper: pulls the value for "key" out of a flat JSON object string
// like {"mode":"auto","threshold":25.0,"window":"close"}. Good enough for our
// own server's fixed-shape replies; not a general JSON parser.
String jsonString(const String& body, const char* key) {
  String needle = String("\"") + key + "\":\"";
  int i = body.indexOf(needle);
  if (i < 0) return "";
  i += needle.length();
  int end = body.indexOf('"', i);
  if (end < 0) return "";
  return body.substring(i, end);
}

float jsonNumber(const String& body, const char* key) {
  String needle = String("\"") + key + "\":";
  int i = body.indexOf(needle);
  if (i < 0) return NAN;
  i += needle.length();
  return body.substring(i).toFloat();
}


// ── HTTP helpers to the Flask webapp ────────────────────────────────────────────

// GET /api/outdoor-temp?token=...  ->  {"outdoor_temp": 27.3}
void fetchOutdoorTemperature() {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT +
               "/api/outdoor-temp?token=" + DEVICE_TOKEN;

  http.setTimeout(HTTP_TIMEOUT_MS);
  if (http.begin(client, url)) {
    int code = http.GET();
    if (code == 200) {
      String body = http.getString();
      float t = jsonNumber(body, "outdoor_temp");
      if (!isnan(t)) {
        externalTemperature = t;
        Serial.print("[HTTP] Outdoor temperature: ");
        Serial.print(externalTemperature, 1);
        Serial.println(" C");
      }
    } else if (code == 503) {
      Serial.println("[HTTP] Outdoor temperature not available yet");
    } else {
      Serial.print("[HTTP] outdoor-temp request failed, code ");
      Serial.println(code);
    }
    http.end();
  } else {
    Serial.println("[HTTP] Could not start outdoor-temp request");
  }
}

// POST /api/report?token=...&indoor=...&people=...&fire=...&ac=...&windows=...
// Replies with {"mode":"...","threshold":...,"window":"..."} so we refresh
// acMode / acThreshold / windowCommand in the same round-trip.
void reportToServer(float indoorTemp, bool fireNow, const char* acBlowing) {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT +
               "/api/report?token=" + DEVICE_TOKEN +
               "&indoor=" + String(indoorTemp, 1) +
               "&people=" + String(peopleInside) +
               "&fire="   + (fireNow ? "1" : "0") +
               "&ac="     + acBlowing +
               "&windows=" + (windowsOpen ? "open" : "closed");  // report ACTUAL state

  http.setTimeout(HTTP_TIMEOUT_MS);
  if (http.begin(client, url)) {
    int code = http.POST("");
    if (code == 200) {
      String body = http.getString();
      String newMode = jsonString(body, "mode");
      float newThreshold = jsonNumber(body, "threshold");
      String newWindow = jsonString(body, "window");
      if (newMode.length() > 0) acMode = newMode;
      if (!isnan(newThreshold)) acThreshold = newThreshold;
      if (newWindow.length() > 0) windowCommand = newWindow;
    } else {
      Serial.print("[HTTP] report failed, code ");
      Serial.println(code);
    }
    http.end();
  } else {
    Serial.println("[HTTP] Could not start report request");
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

  pinMode(IR_FLAME_PIN, INPUT_PULLUP);
  pinMode(SENSOR_1_PIN, INPUT);
  pinMode(SENSOR_2_PIN, INPUT);

  initializeSensorFilter(sensor1Filter, SENSOR_1_PIN);
  initializeSensorFilter(sensor2Filter, SENSOR_2_PIN);

  // Connect to iPhone hotspot
  connectWiFi();

  // First outdoor-temperature fetch immediately after boot
  fetchOutdoorTemperature();
  lastOutdoorPoll = millis();

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

  // ── 1. Outdoor temperature, every 15 seconds ──────────────────────────────
  if (millis() - lastOutdoorPoll >= OUTDOOR_POLL_MS) {
    lastOutdoorPoll = millis();
    fetchOutdoorTemperature();

    if (!isnan(externalTemperature)) {
      Serial.print("[EXT TEMP] Current outdoor temperature: ");
      Serial.print(externalTemperature, 1);
      Serial.println(" C");
    }
  }

  // ── 2. People counter (non-blocking, runs every iteration) ────────────────
  updatePeopleCounter();

  // ── 3. DHT11 local temperature read ───────────────────────────────────────
  float temp = dht.readTemperature();

  if (isnan(temp)) {
    Serial.println("Failed to read from DHT11");
    // Do NOT return here: the fire sensor check below must still run.
    // Fall through with temp = NAN; reportToServer handles NAN gracefully.
  }

  // ── 4. Decide what the AC should do, based on the owner's chosen mode ─────
  // signalToSend: '1' = cold air, '2' = hot air, '0' = explicit off, 0 = nothing
  char signalToSend = 0;
  const char* acBlowing = "off";

  if (!isnan(temp)) {
    if (peopleInside <= 0) {
      acBlowing = "off";  // Arduino auto-offs when nobody is inside; nothing to send
    } else if (acMode == "cool") {
      acBlowing = "cool"; signalToSend = '1';
    } else if (acMode == "heat") {
      acBlowing = "heat"; signalToSend = '2';
    } else if (acMode == "off") {
      acBlowing = "off";  signalToSend = '0';
    } else /* auto */ {
      if (temp > acThreshold) { acBlowing = "cool"; signalToSend = '1'; }
      else                    { acBlowing = "heat"; signalToSend = '2'; }
    }

    if (signalToSend) {
      linkSerial.println(signalToSend);
    }

    Serial.print("[DHT11]   Indoor temperature: ");
    Serial.print(temp);
    Serial.print(" C | AC mode: ");
    Serial.print(acMode);
    Serial.print(" | Sent to Arduino: ");
    Serial.println(signalToSend ? String(signalToSend) : String("(none)"));

    // ── 5. Wait for ACK from Arduino ──────────────────────────────────────────
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
  }

  // ── 6. IR Flame sensor check ───────────────────────────────────────────────
  bool fireDetected = (digitalRead(IR_FLAME_PIN) == LOW);
  static bool firePreviouslyDetected = false;  // Bug 1 & 4: track edge

  if (fireDetected && !firePreviouslyDetected) {
    // Rising edge: fire just appeared — send FIRE once (Bug 4)
    Serial.println("FIRE DETECTED! Sending alert to Arduino...");
    linkSerial.println("FIRE");
    firePreviouslyDetected = true;

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

    // The Arduino closes the windows by itself on FIRE; mirror that locally so
    // our reported state and lastWindowCommand stay consistent.
    windowsOpen = false;
    lastWindowCommand = "close";

  } else if (!fireDetected && firePreviouslyDetected) {
    // Falling edge: fire just cleared — send FIRE_OFF (Bug 1)
    Serial.println("Fire cleared. Sending FIRE_OFF to Arduino...");
    linkSerial.println("FIRE_OFF");
    firePreviouslyDetected = false;

    unsigned long offStart = millis();
    String offAck = "";

    while (millis() - offStart < 2000) {
      updatePeopleCounter();
      if (linkSerial.available()) {
        offAck = linkSerial.readStringUntil('\n');
        offAck.trim();
        break;
      }
    }

    if (offAck.length() > 0) {
      Serial.print("Arduino FIRE_OFF ACK: ");
      Serial.println(offAck);
    } else {
      Serial.println("No FIRE_OFF ACK received");
    }
  }

  // ── 7. Forward window command to Arduino if it changed ────────────────────
  if ((windowCommand == "open" || windowCommand == "close") &&
       windowCommand != lastWindowCommand) {

    String cmd = (windowCommand == "open") ? "WINDOW_OPEN" : "WINDOW_CLOSED";
    Serial.print("[WINDOW] Sending to Arduino: ");
    Serial.println(cmd);
    linkSerial.println(cmd);
    lastWindowCommand = windowCommand;

    unsigned long winStart = millis();
    String winAck = "";

    while (millis() - winStart < 2000) {
      updatePeopleCounter();
      if (linkSerial.available()) {
        winAck = linkSerial.readStringUntil('\n');
        winAck.trim();
        break;
      }
    }

    if (winAck.length() > 0) {
      Serial.print("[WINDOW] Arduino ACK: ");
      Serial.println(winAck);

      // Update the ACTUAL state from what the Arduino confirms.
      if (winAck == "ACK_WINDOW_OPEN") {
        windowsOpen = true;
      } else if (winAck == "ACK_WINDOW_CLOSED") {
        windowsOpen = false;
      } else if (winAck == "ACK_WINDOW_BLOCKED") {
        // Arduino refused (e.g. fire active): windows stay closed. Clear the
        // last command so we retry once conditions allow.
        windowsOpen = false;
        lastWindowCommand = "none";
      }
    } else {
      Serial.println("[WINDOW] No ACK received");
      lastWindowCommand = "none";  // allow retry next loop
    }
  }

  // ── 8. Report current state to the webapp (also refreshes mode/threshold/window) ──
  reportToServer(temp, fireDetected, acBlowing);

  // ── 9. Short delay (non-blocking) ─────────────────────────────────────────
  unsigned long delayStart = millis();
  while (millis() - delayStart < 2000) {
    updatePeopleCounter();
    delay(10);
  }
}
