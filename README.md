# SMD Reel Packing Machine

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

```bash
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
 
