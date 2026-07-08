#include <SoftwareSerial.h>
#include <DHT.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiUdp.h>
#include <WiFiClient.h>

// ── Communications Configuration ──────────────────────────────────────────────
const char* WIFI_SSID     = "iPhone di Riccardo";   // hotspot SSID
const char* WIFI_PASSWORD = "riccardo";             // hotspot password
const char* SERVER_IP     = "172.20.10.2";          // IP printed by the server
const uint16_t SERVER_PORT = 8000;                  // must match config/settings.py PORT

// ── Device identity (multi-tenant platform) ───────────────────────────────────
const char* DEVICE_ID    = "dhome-001";
const char* DEVICE_TOKEN = "tok-secret-001";

//  ─────────────────────────────────────────────────────────────────────────────

//  ── Timing ─────────────────────────────────────────────────────────────────────
const unsigned long OUTDOOR_POLL_MS = 15000UL;
const unsigned long REPORT_INTERVAL_MS = 2000UL;
const unsigned long HTTP_TIMEOUT_MS  =  5000UL;
const unsigned long WIFI_RETRY_MS    =  5000UL;

// ── DHT11 ─────────────────────────────────────────────────────────────────────
#define DHTPIN    D4
#define DHTTYPE   DHT11

// ── SoftwareSerial link to Arduino ────────────────────────────────────────────
#define NODE_RX   D5
#define NODE_TX   D6

// ── IR Flame sensor ───────────────────────────────────────────────────────────
#define IR_FLAME_PIN  D1

// ── People counter – IR obstacle sensors (LM393) ─────────────────────────────
const uint8_t SENSOR_1_PIN = D0;   // outside
const uint8_t SENSOR_2_PIN = D2;   // inside
const uint8_t DETECTED_LEVEL = LOW;

// ── Timing Settings ─────────────────────────────────────────────────────────────────────
const unsigned long DEBOUNCE_TIME_MS    =   35;
const unsigned long PASSAGE_TIMEOUT_MS  = 1200;
const unsigned long REARM_TIME_MS       =  250;

DHT dht(DHTPIN, DHTTYPE);
SoftwareSerial linkSerial(NODE_RX, NODE_TX);

// ── People-counter variables ───────────────────────────────────────────────────
int  peopleInside  = 0;
unsigned long totalEntries = 0;
unsigned long totalExits   = 0;

// ── External temperature ──────────────────────────────
float externalTemperature = NAN;
unsigned long lastOutdoorPoll = 0;

// ── Owner's desired AC behaviour ─────────────────────
String acMode      = "auto";
float  acThreshold  = 25.0;

// ── Window state ──────────────────────────────────────────────────────────────
String windowCommand     = "none";
String lastWindowCommand = "none";
bool   windowsOpen       = false;

// ── Sensor debouncing ─────────────────────────────────────────────────────────
struct SensorFilter { bool rawState; bool stableState; unsigned long lastChangeTime; };
SensorFilter sensor1Filter;
SensorFilter sensor2Filter;

// ── Counter state machine ─────────────────────────────────────────────────────
enum CounterState { IDLE, SENSOR_1_TRIGGERED_FIRST, SENSOR_2_TRIGGERED_FIRST, WAIT_FOR_CLEAR };
CounterState currentState = IDLE;
unsigned long sequenceStartTime = 0;
unsigned long clearStartTime    = 0;


// ── WiFi helpers ──────────────────────────────────────────────────────────────
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("[WiFi] Connecting to "); Serial.print(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000UL) { delay(500); Serial.print("."); }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(); Serial.print("[WiFi] Connected! NodeMCU IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println(); Serial.println("[WiFi] Connection failed. Will retry later.");
  }
}

// ── JSON value extractors ─────────────────────────────────────────────────
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

// ── HTTP helpers ────────────────────────────────────────────────────────────
void fetchOutdoorTemperature() {
  if (WiFi.status() != WL_CONNECTED) return;
  WiFiClient client; HTTPClient http;
  // device_id + token identify this device to the server.
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT +
               "/api/outdoor-temp?device_id=" + DEVICE_ID + "&token=" + DEVICE_TOKEN;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (http.begin(client, url)) {
    int code = http.GET();
    if (code == 200) {
      String body = http.getString();
      float t = jsonNumber(body, "outdoor_temp");
      if (!isnan(t)) {
        externalTemperature = t;
        Serial.print("[HTTP] Outdoor temperature: "); Serial.print(externalTemperature, 1); Serial.println(" C");
      }
    } else if (code == 503) {
      Serial.println("[HTTP] Outdoor temperature not available yet");
    } else {
      Serial.print("[HTTP] outdoor-temp request failed, code "); Serial.println(code);
    }
    http.end();
  } else {
    Serial.println("[HTTP] Could not start outdoor-temp request");
  }
}

void reportToServer(float indoorTemp, bool fireNow, const char* acBlowing) {
  if (WiFi.status() != WL_CONNECTED) return;
  WiFiClient client; HTTPClient http;
  // /api/report is now POST + JSON only: device_id/token never sit in the
  // URL (so they can't leak through server/proxy access logs) -- the token
  // travels only in the Authorization header, over the request actually
  // proving possession of it.
  String url = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/api/report";

  String body = String("{") +
    "\"device_id\":\"" + DEVICE_ID + "\"," +
    "\"indoor\":\""    + String(indoorTemp, 1) + "\"," +
    "\"people\":\""    + String(peopleInside) + "\"," +
    "\"fire\":\""      + (fireNow ? "1" : "0") + "\"," +
    "\"ac\":\""        + acBlowing + "\"," +
    "\"windows\":\""   + (windowsOpen ? "open" : "closed") + "\"" +
  "}";

  http.setTimeout(HTTP_TIMEOUT_MS);
  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
    int code = http.POST(body);
    if (code == 200) {
      String respBody = http.getString();
      String newMode = jsonString(respBody, "mode");
      float newThreshold = jsonNumber(respBody, "threshold");
      String newWindow = jsonString(respBody, "window");
      if (newMode.length() > 0) acMode = newMode;
      if (!isnan(newThreshold)) acThreshold = newThreshold;
      if (newWindow.length() > 0) windowCommand = newWindow;
    } else {
      Serial.print("[HTTP] report failed, code "); Serial.println(code);
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
  if (currentRawState != filter.rawState) { filter.rawState = currentRawState; filter.lastChangeTime = currentTime; }
  if (filter.stableState != filter.rawState && currentTime - filter.lastChangeTime >= DEBOUNCE_TIME_MS)
    filter.stableState = filter.rawState;
  return filter.stableState;
}
void initializeSensorFilter(SensorFilter &filter, uint8_t pin) {
  bool detected = (digitalRead(pin) == DETECTED_LEVEL);
  filter.rawState = detected; filter.stableState = detected; filter.lastChangeTime = millis();
}

// ── Counter event handlers ────────────────────────────────────────────────────
void sendPeopleInsideFlag() {
  if (peopleInside > 0) { linkSerial.println("PEOPLE_INSIDE:1"); Serial.println("    [flag] PEOPLE_INSIDE:1 sent"); }
  else                  { linkSerial.println("PEOPLE_INSIDE:0"); Serial.println("    [flag] PEOPLE_INSIDE:0 sent"); }
}
void registerEntry() {
  totalEntries++; peopleInside++;
  Serial.println(">>> ENTRY detected"); sendPeopleInsideFlag();
  currentState = WAIT_FOR_CLEAR; clearStartTime = 0;
}
void registerExit() {
  totalExits++; if (peopleInside > 0) peopleInside--;
  Serial.println("<<< EXIT detected"); sendPeopleInsideFlag();
  currentState = WAIT_FOR_CLEAR; clearStartTime = 0;
}

// ── People counter ─────────────────
void updatePeopleCounter() {
  bool s1 = readDebouncedSensor(sensor1Filter, SENSOR_1_PIN);
  bool s2 = readDebouncedSensor(sensor2Filter, SENSOR_2_PIN);
  unsigned long currentTime = millis();
  switch (currentState) {
    case IDLE:
      if (s1 && s2) { currentState = WAIT_FOR_CLEAR; clearStartTime = 0; }
      else if (s1) { currentState = SENSOR_1_TRIGGERED_FIRST; sequenceStartTime = currentTime; }
      else if (s2) { currentState = SENSOR_2_TRIGGERED_FIRST; sequenceStartTime = currentTime; }
      break;
    case SENSOR_1_TRIGGERED_FIRST:
      if (s2) registerEntry();
      else if (currentTime - sequenceStartTime > PASSAGE_TIMEOUT_MS)
        currentState = (s1 || s2) ? WAIT_FOR_CLEAR : IDLE;
      break;
    case SENSOR_2_TRIGGERED_FIRST:
      if (s1) registerExit();
      else if (currentTime - sequenceStartTime > PASSAGE_TIMEOUT_MS)
        currentState = (s1 || s2) ? WAIT_FOR_CLEAR : IDLE;
      break;
    case WAIT_FOR_CLEAR:
      if (!s1 && !s2) {
        if (clearStartTime == 0) clearStartTime = currentTime;
        if (currentTime - clearStartTime >= REARM_TIME_MS) { currentState = IDLE; clearStartTime = 0; }
      } else clearStartTime = 0;
      break;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  linkSerial.begin(9600);
  dht.begin();
  pinMode(IR_FLAME_PIN, INPUT_PULLUP);
  pinMode(SENSOR_1_PIN, INPUT);
  pinMode(SENSOR_2_PIN, INPUT);
  initializeSensorFilter(sensor1Filter, SENSOR_1_PIN);
  initializeSensorFilter(sensor2Filter, SENSOR_2_PIN);
  connectWiFi();
  fetchOutdoorTemperature();
  lastOutdoorPoll = millis();
  Serial.print("NodeMCU ready as device "); Serial.println(DEVICE_ID);
}

void loop() {
  static unsigned long lastWifiCheck = 0;
  if (millis() - lastWifiCheck > WIFI_RETRY_MS) {
    lastWifiCheck = millis();
    if (WiFi.status() != WL_CONNECTED) { Serial.println("[WiFi] lost – reconnecting..."); connectWiFi(); }
  }
  if (millis() - lastOutdoorPoll >= OUTDOOR_POLL_MS) {
    lastOutdoorPoll = millis();
    fetchOutdoorTemperature();
  }

  updatePeopleCounter();

  float temp = dht.readTemperature();
  if (isnan(temp)) Serial.println("Failed to read from DHT11");

  char signalToSend = 0;
  const char* acBlowing = "off";
  if (!isnan(temp)) {
    if (acMode == "cool")      { acBlowing = "cool"; signalToSend = '1'; }
    else if (acMode == "heat") { acBlowing = "heat"; signalToSend = '2'; }
    else if (acMode == "off")  { acBlowing = "off";  signalToSend = '0'; }
    else { // auto
      if (temp > acThreshold) { acBlowing = "cool"; signalToSend = '1'; }
      else                    { acBlowing = "heat"; signalToSend = '2'; }
    }
    if (signalToSend) linkSerial.println(signalToSend);

    unsigned long startTime = millis();
    String ack = "";
    while (millis() - startTime < 1000) {
      updatePeopleCounter();
      if (linkSerial.available()) { ack = linkSerial.readStringUntil('\n'); ack.trim(); break; }
    }
  }

  bool fireDetected = (digitalRead(IR_FLAME_PIN) == LOW);
  static bool firePreviouslyDetected = false;
  if (fireDetected && !firePreviouslyDetected) {
    Serial.println("FIRE DETECTED! Sending alert...");
    linkSerial.println("FIRE");
    firePreviouslyDetected = true;
    unsigned long fireStart = millis(); String fireAck = "";
    while (millis() - fireStart < 4000) { updatePeopleCounter();
      if (linkSerial.available()) { fireAck = linkSerial.readStringUntil('\n'); fireAck.trim(); break; } }
    windowsOpen = false; lastWindowCommand = "close";
  } else if (!fireDetected && firePreviouslyDetected) {
    Serial.println("Fire cleared. Sending FIRE_OFF...");
    linkSerial.println("FIRE_OFF");
    firePreviouslyDetected = false;
    unsigned long offStart = millis(); String offAck = "";
    while (millis() - offStart < 2000) { updatePeopleCounter();
      if (linkSerial.available()) { offAck = linkSerial.readStringUntil('\n'); offAck.trim(); break; } }
  }

  if ((windowCommand == "open" || windowCommand == "close") && windowCommand != lastWindowCommand) {
    String cmd = (windowCommand == "open") ? "WINDOW_OPEN" : "WINDOW_CLOSED";
    Serial.print("[WINDOW] Sending: "); Serial.println(cmd);
    linkSerial.println(cmd);
    lastWindowCommand = windowCommand;
    unsigned long winStart = millis(); String winAck = "";
    while (millis() - winStart < 2000) { updatePeopleCounter();
      if (linkSerial.available()) { winAck = linkSerial.readStringUntil('\n'); winAck.trim(); break; } }
    if (winAck == "ACK_WINDOW_OPEN") windowsOpen = true;
    else if (winAck == "ACK_WINDOW_CLOSED") windowsOpen = false;
    else if (winAck == "ACK_WINDOW_BLOCKED") { windowsOpen = false; lastWindowCommand = "none"; }
    else if (winAck.length() == 0) lastWindowCommand = "none";
  }

  reportToServer(temp, fireDetected, acBlowing);

  unsigned long delayStart = millis();
  while (millis() - delayStart < REPORT_INTERVAL_MS) { updatePeopleCounter(); delay(10); }
}
