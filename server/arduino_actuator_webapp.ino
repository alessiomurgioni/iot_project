#include <SoftwareSerial.h>

// ── Outputs ──────────────────────────────────────────────────────────────────
#define RED_LED     10  // HOT AIR
#define BLUE_LED    11  // COLD AIR
#define YELLOW_LED   9  // FIRE ALARM SYSTEM
#define WHITE_LED    4  // WINDOW: ON = open, OFF = closed

// ── Serial communication with NodeMCU ────────────────────────────────────────
#define UNO_RX 2   // Receives from NodeMCU TX
#define UNO_TX 3   // Sends to NodeMCU RX

SoftwareSerial linkSerial(UNO_RX, UNO_TX); // RX, TX


// ── General state variables ──────────────────────────────────────────────────
bool fireActive = false;
bool fireEventLatched = false;  // Prevents repeated FIRE messages restarting alarm

bool windowOpen = false;
bool peopleInside = false;

// 0 = AC explicitly off (owner chose Off, or no command received yet)
// 1 = cold air
// 2 = hot air
char requestedAcMode = '0';


// ── Fire alarm variables ─────────────────────────────────────────────────────
const unsigned long FIRE_ALARM_DURATION_MS = 30000UL; // 30 seconds
const unsigned long BLINK_INTERVAL_MS = 500UL;

unsigned long fireAlarmStartTime = 0;
unsigned long lastBlinkTime = 0;

bool yellowState = false;


// ── Window helper ────────────────────────────────────────────────────────────
void setWindow(bool open) {
  windowOpen = open;
  digitalWrite(WHITE_LED, open ? HIGH : LOW);

  if (open) {
    Serial.println("Window OPENED");
  } else {
    Serial.println("Window CLOSED");
  }
}


// ── Air conditioning helpers ─────────────────────────────────────────────────
void turnOffAirConditioning() {
  digitalWrite(RED_LED, LOW);
  digitalWrite(BLUE_LED, LOW);

  Serial.println("Air conditioning OFF");
}


void updateAirConditioning() {
  // Do not run AC if nobody is inside
  if (!peopleInside) {
    turnOffAirConditioning();
    return;
  }

  // Cold air
  if (requestedAcMode == '1') {
    digitalWrite(BLUE_LED, HIGH);
    digitalWrite(RED_LED, LOW);

    Serial.println("Cold air ON");
  }

  // Hot air
  else if (requestedAcMode == '2') {
    digitalWrite(RED_LED, HIGH);
    digitalWrite(BLUE_LED, LOW);

    Serial.println("Hot air ON");
  }

  // Explicitly off (owner chose Off) or no command received yet
  else {
    turnOffAirConditioning();
    if (requestedAcMode == '0') {
      Serial.println("AC explicitly OFF (owner command)");
    } else {
      Serial.println("Waiting for temperature command");
    }
  }
}


// ── Fire alarm helpers ───────────────────────────────────────────────────────
void startFireAlarm() {
  fireActive = true;
  fireEventLatched = true;

  yellowState = false;
  digitalWrite(YELLOW_LED, LOW);

  fireAlarmStartTime = millis();
  lastBlinkTime = millis();

  // Close window during fire event
  if (windowOpen) {
    setWindow(false);
    Serial.println("Window closed due to FIRE signal");
  }

  Serial.println("FIRE alarm started: duration 30 seconds");
}


void stopFireAlarm() {
  fireActive = false;

  yellowState = false;
  digitalWrite(YELLOW_LED, LOW);

  Serial.println("FIRE alarm stopped");
}


// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  pinMode(RED_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(WHITE_LED, OUTPUT);

  digitalWrite(RED_LED, LOW);
  digitalWrite(BLUE_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(WHITE_LED, LOW);

  Serial.begin(9600);
  linkSerial.begin(9600);

  Serial.println("Arduino Uno ready");
  Serial.println("AC starts OFF until PEOPLE_INSIDE:1 is received");
}


// ─────────────────────────────────────────────────────────────────────────────
void loop() {

  // ── Handle incoming messages from NodeMCU ──────────────────────────────────
  if (linkSerial.available()) {
    String received = linkSerial.readStringUntil('\n');
    received.trim();

    Serial.print("Received: ");
    Serial.println(received);

    // ── People inside: enable AC automation ──────────────────────────────────
    if (received == "PEOPLE_INSIDE:1") {
      peopleInside = true;

      Serial.println("People detected inside: AC automation ENABLED");
      updateAirConditioning();

      // No ACK: NodeMCU does not wait for one for this message.
    }

    // ── Nobody inside: turn AC off ───────────────────────────────────────────
    else if (received == "PEOPLE_INSIDE:0") {
      peopleInside = false;

      Serial.println("Nobody inside: AC automation DISABLED");
      turnOffAirConditioning();

      // No ACK: NodeMCU does not wait for one for this message.
    }

    // ── Temperature command: cold air ────────────────────────────────────────
    else if (received == "1") {
      requestedAcMode = '1';

      if (peopleInside) {
        updateAirConditioning();
      } else {
        turnOffAirConditioning();
        Serial.println("Cold-air request saved, but nobody is inside");
      }

      linkSerial.println("ACK1");
    }

    // ── Temperature command: hot air ─────────────────────────────────────────
    else if (received == "2") {
      requestedAcMode = '2';

      if (peopleInside) {
        updateAirConditioning();
      } else {
        turnOffAirConditioning();
        Serial.println("Hot-air request saved, but nobody is inside");
      }

      linkSerial.println("ACK2");
    }

    // ── AC command: explicit off (owner chose "Off" on the dashboard) ────────
    else if (received == "0") {
      requestedAcMode = '0';
      turnOffAirConditioning();
      Serial.println("AC explicitly turned OFF by owner command");

      linkSerial.println("ACK0");
    }

    // ── Fire detected ────────────────────────────────────────────────────────
    else if (received == "FIRE") {
      // Start alarm only once for each fire event
      if (!fireEventLatched) {
        startFireAlarm();
      } else {
        Serial.println("FIRE ignored: event already handled");
      }

      linkSerial.println("ACK_FIRE");
    }

    // ── Fire no longer detected: re-arm the alarm for future events ──────────
    else if (received == "FIRE_OFF") {
      stopFireAlarm();
      fireEventLatched = false;

      linkSerial.println("ACK_FIRE_OFF");
      Serial.println("System re-armed for a future fire event");
    }

    // ── Window toggle ────────────────────────────────────────────────────────
    else if (received == "WINDOW") {
      // Do not allow window opening while fire is active
      if (fireActive && !windowOpen) {
        Serial.println("WINDOW ignored: fire alarm is active");
        linkSerial.println("ACK_WINDOW_BLOCKED");
      } else {
        setWindow(!windowOpen);

        if (windowOpen) {
          linkSerial.println("ACK_WINDOW_OPEN");
        } else {
          linkSerial.println("ACK_WINDOW_CLOSED");
        }
      }
    }
  }


  // ── Fire alarm blinking and 30-second automatic timeout ────────────────────
  if (fireActive) {
    unsigned long currentTime = millis();

    // End alarm after 30 seconds
    if (currentTime - fireAlarmStartTime >= FIRE_ALARM_DURATION_MS) {
      stopFireAlarm();

      // fireEventLatched remains true:
      // repeated FIRE messages cannot restart the alarm until FIRE_OFF arrives.
      Serial.println("Fire alarm automatically stopped after 30 seconds");
    }

    // Blink yellow LED while alarm is active
    else if (currentTime - lastBlinkTime >= BLINK_INTERVAL_MS) {
      lastBlinkTime = currentTime;

      yellowState = !yellowState;
      digitalWrite(YELLOW_LED, yellowState ? HIGH : LOW);
    }
  }
}
