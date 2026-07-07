#include <SoftwareSerial.h>

// ── Outputs ──────────────────────────────────────────────────────────────────
#define RED_LED     10  // HOT AIR
#define BLUE_LED    11  // COLD AIR
#define YELLOW_LED   9  // FIRE ALARM SYSTEM
#define WHITE_LED    4  // WINDOW: ON = open, OFF = closed

// ── Serial link to NodeMCU ────────────────────────────────────────────────────
#define UNO_RX 2   // Receives from NodeMCU TX
#define UNO_TX 3   // Sends to NodeMCU RX
SoftwareSerial linkSerial(UNO_RX, UNO_TX);

// ── State ─────────────────────────────────────────────────────────────────────
bool fireActive = false;
bool fireEventLatched = false;
bool windowOpen = false;
bool peopleInside = false;
char requestedAcMode = '0';   // 0 off, 1 cold, 2 hot

// ── Fire alarm ────────────────────────────────────────────────────────────────
const unsigned long FIRE_ALARM_DURATION_MS = 30000UL;
const unsigned long BLINK_INTERVAL_MS = 500UL;
unsigned long fireAlarmStartTime = 0;
unsigned long lastBlinkTime = 0;
bool yellowState = false;

void turnOffAirConditioning();

void setWindow(bool open) {
  windowOpen = open;
  digitalWrite(WHITE_LED, open ? HIGH : LOW);
  if (open) { Serial.println("Window OPENED"); turnOffAirConditioning(); }
  else Serial.println("Window CLOSED");
}

void turnOffAirConditioning() {
  digitalWrite(RED_LED, LOW);
  digitalWrite(BLUE_LED, LOW);
  Serial.println("Air conditioning OFF");
}

void updateAirConditioning() {
  if (windowOpen) { turnOffAirConditioning(); Serial.println("AC held off: windows open"); return; }
  if (requestedAcMode == '1') { digitalWrite(BLUE_LED, HIGH); digitalWrite(RED_LED, LOW); Serial.println("Cold air ON"); }
  else if (requestedAcMode == '2') { digitalWrite(RED_LED, HIGH); digitalWrite(BLUE_LED, LOW); Serial.println("Hot air ON"); }
  else turnOffAirConditioning();
}

void startFireAlarm() {
  fireActive = true; fireEventLatched = true;
  yellowState = false; digitalWrite(YELLOW_LED, LOW);
  fireAlarmStartTime = millis(); lastBlinkTime = millis();
  if (windowOpen) { setWindow(false); Serial.println("Window closed due to FIRE"); }
  Serial.println("FIRE alarm started (30s)");
}

void stopFireAlarm() {
  fireActive = false; yellowState = false; digitalWrite(YELLOW_LED, LOW);
  Serial.println("FIRE alarm stopped");
}

void setup() {
  pinMode(RED_LED, OUTPUT); pinMode(BLUE_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT); pinMode(WHITE_LED, OUTPUT);
  digitalWrite(RED_LED, LOW); digitalWrite(BLUE_LED, LOW);
  digitalWrite(YELLOW_LED, LOW); digitalWrite(WHITE_LED, LOW);
  Serial.begin(9600); linkSerial.begin(9600);
  Serial.println("Arduino Uno ready");
}

void loop() {
  if (linkSerial.available()) {
    String received = linkSerial.readStringUntil('\n');
    received.trim();
    Serial.print("Received: "); Serial.println(received);

    if (received == "PEOPLE_INSIDE:1") { peopleInside = true; updateAirConditioning(); }
    else if (received == "PEOPLE_INSIDE:0") { peopleInside = false; turnOffAirConditioning(); }
    else if (received == "1") { requestedAcMode = '1'; updateAirConditioning(); linkSerial.println("ACK1"); }
    else if (received == "2") { requestedAcMode = '2'; updateAirConditioning(); linkSerial.println("ACK2"); }
    else if (received == "0") { requestedAcMode = '0'; turnOffAirConditioning(); linkSerial.println("ACK0"); }
    else if (received == "FIRE") {
      if (!fireEventLatched) startFireAlarm(); else Serial.println("FIRE ignored: already handled");
      linkSerial.println("ACK_FIRE");
    }
    else if (received == "FIRE_OFF") {
      stopFireAlarm(); fireEventLatched = false; linkSerial.println("ACK_FIRE_OFF");
    }
    else if (received == "WINDOW_OPEN") {
      if (fireActive) linkSerial.println("ACK_WINDOW_BLOCKED");
      else { setWindow(true); linkSerial.println("ACK_WINDOW_OPEN"); }
    }
    else if (received == "WINDOW_CLOSED") {
      setWindow(false);
      if (peopleInside) updateAirConditioning();
      linkSerial.println("ACK_WINDOW_CLOSED");
    }
  }

  if (fireActive) {
    unsigned long now = millis();
    if (now - fireAlarmStartTime >= FIRE_ALARM_DURATION_MS) {
      stopFireAlarm(); Serial.println("Fire alarm auto-stopped after 30s");
    } else if (now - lastBlinkTime >= BLINK_INTERVAL_MS) {
      lastBlinkTime = now; yellowState = !yellowState;
      digitalWrite(YELLOW_LED, yellowState ? HIGH : LOW);
    }
  }
}
