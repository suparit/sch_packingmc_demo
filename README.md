


# SMD Reel Packing Machine

## What This Repo Is

This is a lightweight Digital Twin system for SMD Reel Packing Machine:
- Process definition
- State machine
- 3D visualization
- Local simulation


## START
- Power ON
- Set Parameter
  - Speed
  - Temperature
  - Pressure
  - Count

## Material Setup
- Load Carrier Tape
- Load Cover Tape

## Feeding Process
- Feed Carrier Tape to index position
- Check Position Sensor
  - OK → Next
  - NG → Alarm

## Loading
- Load component into pocket

## Vision Inspection
- Check:
  - Presence
  - Position
  - Orientation
- Result
  - OK → Next
  - NG → Alarm

## Cover Tape Process
- Feed Cover Tape

## Temperature Control
- Check Temperature Ready
  - Ready → Next
  - Not Ready → Wait

## Sealing
- Heat
- Pressure

## Seal Inspection
- Check Quality
  - Seal complete
  - No damage
  - No wrinkle
- Result
  - OK → Next
  - NG → Alarm

## Output
- Roll finished tape to reel

## Count Control
- Check quantity
  - Reached → STOP
  - Not reached → Loop back to Feeding

## STOP

## ALARM
- Stop machine
- Show error

---

## Digital Twin (3D Viewer)

This project includes a simple 3D web viewer for demonstration and simulation.

### Online (Viewer Only)

Open in browser:
https://suparit.github.io/sch_packingmc_demo/cad/viewer.html

- View machine in 3D
- Rotate / zoom
- Mobile supported

---

### Local Simulation (Recommended)

For motion testing (e.g. cylinder extend/retract):

#### Method 1 (Simple)

Double click:
 run_server.bat
Then open:

http://localhost:8080/cad/viewer_local.html

---

#### Method 2 (Manual)

Run:
bash
python -m http.server 8080

Open:
http://localhost:8080/cad/viewer_local.html


Notes

GitHub Pages = Viewer only (no control)
Local mode = Simulation / motion test
Models are stored in cad/export/


Model Concept

machine.glb → static machine
cylinder.glb → moving part

Motion is implemented using JavaScript (simple linear movement)

Future Work

FSM (machine state control)
Modbus → Web integration
Multi-axis motion
Full Digital Twin synchronization

---

## Knowledge Map (Start Here)

This repository is organized into several parts:

### 1. Machine Process
- README.md
- Defines full machine workflow (START → STOP)

### 2. State Machine (Control Logic)
- SMD Reel Packing FSM (Simple).md
- Defines machine states and transitions

### 3. 3D Digital Twin (Visualization)
- cad/
- viewer.html → online view
- viewer_local.html → local simulation

### 4. Control & Test
- demo_001.py → Modbus / IO test
- run_server.bat → local web server

### 5. Architecture & Design
- ARCHITECTURE_3D_TWIN.md → system design
- Lightweight Digital Twin Roadmap.md → future direction

### 6. Project Plan
- projectplan.md → timeline and progress

---

Recommended reading order:

1. Machine Process (this file)
2. FSM (logic)
3. 3D Viewer (visual)
4. Architecture (design)


## Architecture Decision Records (ADR)


### ✅ Completed
- ADR-001: Encoder and Counter Selection  
  → docs/decisions/ADR_001_encoder_counter.md

### 🔄 TODO
- ADR-002: Motor Selection
- ADR-003: Pin Mechanism Design
- ADR-004: Sensor Selection


