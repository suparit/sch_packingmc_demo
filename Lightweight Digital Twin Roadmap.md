Lightweight Digital Twin Roadmap

Vision

Build a lightweight, portable, browser-based Digital Twin framework for industrial machines.

The goal is not to create a high-end physics simulation.

The goal is to create a practical machine representation that connects:

Machine State
    +
Machine Events
    +
Machine Visualization

using simple, maintainable, and deployable technologies.

---

Core Philosophy

Portable First

No Install
No Admin Rights
Zip → Run → Done

The system should run on:

- Engineering Laptop
- Factory PC
- Industrial IPC
- Local Server

without requiring complex deployment.

---

State-Driven Architecture

The Digital Twin is driven by machine state.

Not by pre-recorded animation.

PLC State
      ↓
State Engine
      ↓
3D Motion

Motion is generated at runtime.

---

Browser Native

The browser is the runtime.

GLB
+
JavaScript
+
Web Browser

No Unity dependency.

No Unreal dependency.

No proprietary runtime.

---

Architecture

+---------------------+
|      PLC / IO       |
+---------------------+
           |
           v
+---------------------+
|      OPC UA         |
+---------------------+
           |
           v
+---------------------+
|   State Engine      |
+---------------------+
           |
           v
+---------------------+
|  Twin Runtime       |
+---------------------+
           |
           v
+---------------------+
| Browser Viewer      |
| model-viewer        |
| Three.js (future)   |
+---------------------+

---

Roadmap

Phase 0 — Concept Validation

Goal:

Verify that machine parts can be visualized independently.

Deliverables:

- CAD Assembly
- Export GLB Parts
- Load Parts in Browser
- Manual Motion Control

Success Criteria:

- Individual part movement works
- Rotation and translation work correctly

Status:

- In Progress

---

Phase 1 — Machine Visualization

Goal:

Create a visual machine monitor.

Deliverables:

- Cylinder Motion
- Rotary Motion
- Sensor Indicator
- Machine Status Display

Success Criteria:

- Machine state can be observed visually

Status:

- Planned

---

Phase 2 — State Engine

Goal:

Represent machine logic using finite state machines.

Example:

IDLE
 ↓
LOAD
 ↓
CLAMP
 ↓
PROCESS
 ↓
UNLOAD

Deliverables:

- FSM Engine
- State Transition Logic
- State Visualization

Success Criteria:

- Visualization follows state changes

Status:

- Planned

---

Phase 3 — Live Machine Connection

Goal:

Connect real machine data.

Deliverables:

- OPC UA Client
- WebSocket Gateway
- Tag Mapping Layer

Example:

PLC Tag
    ↓
State Engine
    ↓
Twin Motion

Success Criteria:

- Real machine drives visualization

Status:

- Planned

---

Phase 4 — Event Replay

Goal:

Replay machine history.

Deliverables:

- Event Logger
- Cycle Recorder
- Alarm Recorder
- Replay Engine

Success Criteria:

- Historical machine operation can be replayed

Status:

- Planned

---

Phase 5 — Digital Twin Runtime

Goal:

Create reusable framework components.

Modules:

Asset Manager
State Engine
Event Logger
OPC Connector
Twin Viewer
Rule Engine

Success Criteria:

- New machines can be added with configuration

Status:

- Future

---

Non-Goals

The project does NOT aim to become:

- Full CAD software
- Physics simulation engine
- SCADA replacement
- PLC replacement
- MES replacement

The Digital Twin is a visualization and state representation layer.

---

Long-Term Direction

Machine
    ↓
State
    ↓
Events
    ↓
Digital Representation
    ↓
Engineering Insight

The Digital Twin becomes a bridge between:

- Automation
- Visualization
- Diagnostics
- AI Agents
- Engineering Knowledge

without losing simplicity.

---

Current Principle

Start with one machine.

Make it work.

Then generalize.

Do not build a platform before proving the concept.
