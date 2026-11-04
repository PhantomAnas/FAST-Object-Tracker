# Arduino / serial output

FAST Object Tracker can write a short serial message every time an object is
counted (or only when an alarm fires). Any board that shows up as a USB serial
port works: Arduino Uno/Nano/Mega, ESP32, ESP8266, Raspberry Pi Pico, CH340
clones... The board decides what to do with the message: pulse a relay, light
an LED, click a counter, trigger a label printer, drive a 7-segment display.

## 1. Flash the sketch

The default message is `Go\r` (the text `Go` followed by a carriage return).
This sketch pulses pin 7 HIGH for 200 ms each time it arrives, and blinks the
on-board LED so you can see it working without any wiring.

```cpp
// FAST Object Tracker - relay pulse on every count
const int RELAY_PIN = 7;        // relay module IN pin (or any output)
const unsigned long PULSE_MS = 200;

String buffer;

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);
  Serial.begin(9600);           // must match the baud rate in the app
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (buffer == "Go") pulse();
      buffer = "";
    } else {
      buffer += c;
      if (buffer.length() > 32) buffer = "";
    }
  }
}

void pulse() {
  digitalWrite(RELAY_PIN, HIGH);
  digitalWrite(LED_BUILTIN, HIGH);
  delay(PULSE_MS);
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(LED_BUILTIN, LOW);
}
```

Upload it with the Arduino IDE, then close the IDE's Serial Monitor (only one
program can hold the port).

## 2. Wiring a relay module

Typical 5 V single-channel relay module:

| Relay module | Arduino |
|--------------|---------|
| VCC          | 5V      |
| GND          | GND     |
| IN           | D7      |

Switch the load (lamp, buzzer, PLC input, printer trigger) through the relay's
COM / NO terminals. For a 12 V or 24 V machine input use the relay as a dry
contact; never feed mains or machine voltages into the Arduino itself.

Many relay modules are *active-low*: if yours clicks on start-up and releases
on a count, swap `HIGH` and `LOW` in `pulse()` and in `setup()`.

## 3. Settings in the app

Open the **Arduino / serial output** card:

- **Send a serial message** - turn it on.
- **Port** - `auto` picks the first USB serial device (anything whose
  description mentions USB, Arduino, CH340, CP210x, FTDI or WCH). Pick a port
  by name if you have several boards.
- **Baud** - 9600 unless you changed `Serial.begin`.
- **Message** - `Go\r` by default. Escapes `\r`, `\n`, `\t` are understood,
  so `COUNT\n` sends `COUNT` plus a newline.
- **Send on** - *Every count*, *Alarms only* (only when an alarm rule with the
  `serial` or `beep+serial` action fires), or *Never* (use the Test button to
  check the wiring).
- **Test: send now** - writes one message immediately.

The *Serial* light in the top bar turns green when the port is open and red
if the board is unplugged; the app keeps retrying every few seconds and logs
when it reconnects. Counting continues without the board.

From the command line:

```
fasttracker --cli --source 0 --classes bottle --serial --serial-port COM7 --serial-message "Go\r"
fasttracker --cli --list-ports
```

## 4. Doing more on the board

Because the whole count is on the PC side, the board only needs to react to
messages. Ideas:

- Send a different message per class with two alarm rules (`bottle:1:serial`
  with repeat, and the global message for the rest) and branch on the text.
- Put the running total in the message, e.g. `COUNT 42\n`, and show it on an
  LCD or 7-segment display - the message is any text you type.
- ESP32/ESP8266 boards can forward the pulse over Wi-Fi or MQTT.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "no serial port found" | Install the board's USB driver (CH340 / CP210x) and check Device Manager. |
| "could not open COMx: Access is denied" | Another program (Arduino Serial Monitor, a terminal) has the port open. |
| Board resets on connect and misses the first counts | Normal for Uno/Nano (DTR reset). Start tracking, wait two seconds, then reset counts. |
| Relay chatters on every frame | Make sure *Send on* is *Every count*, not a loop in the sketch; the app sends one message per counted object. |
