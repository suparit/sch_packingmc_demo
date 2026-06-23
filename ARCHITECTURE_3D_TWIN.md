# Architecture - 3D Digital Twin

> This document defines how the 3D Digital Twin system is designed, implemented, and evolved.
> Author: Suparit  
> Date: 2026-06-23

---

## 1. Purpose

The 3D Digital Twin is designed to:

- Visualize machine structure in 3D
- Demonstrate machine operation (motion + process)
- Support training and understanding
- Provide a foundation for future integration with real hardware

---

## 2. System Overview

Layered architecture:

CAD Model (Fusion / Blender)
        ↓
GLB Export (Optimized)
        ↓
Web Viewer (model-viewer)
        ↓
JavaScript Motion Control
        ↓
(Optional) Real Machine Integration (Modbus / IO)

---

## 3. Design Philosophy

### 3.1 Keep it Simple (Current Strategy)

The system prioritizes:

- Simplicity
- Fast iteration
- Low resource usage
- Easy usage for non-experts

### 3.2 Why Simplicity

Machine automation is:

- Deterministic
- State-driven
- Timing-controlled

Examples:
- Cylinder → extend / retract
- Feeder → step motion
- Sealing → timed process

Therefore:

> Motion is controlled by FSM (logic), not physics.

---

## 4. Technology Stack

### Viewer Layer
- model-viewer (web component)
- Built on Three.js + WebGL

### Model Format
- GLB format
- Lightweight and optimized for web

### Motion Layer

JavaScript-based transformation:

    translateX(50px)

---

## 5. Model Strategy

### Separation
- machine.glb → static structure
- cylinder.glb → moving part

### Requirement
- Same coordinate origin
- No reposition during export

### Workflow
1. Design in Fusion
2. Optimize in Blender
3. Apply modifier ✅
4. Reduce texture
5. Export GLB

---

## 6. Runtime Modes

### Online Mode
- GitHub Pages
- Viewer only

### Local Mode

Run:

    python -m http.server 8080

Open:

    http://localhost:8080/cad/viewer_local.html

---

## 7. Motion Concept

### Current
- JavaScript transform
- Linear motion only

### Advantages
- Simple
- Fast
- Easy debug

### Limitations
- No physics
- No collision
- Not realistic simulation

---

## 8. Future Architecture

### 8.1 Three.js
- Direct control of scene and objects

### 8.2 Physics Engines
- cannon-es
- ammo.js
- rapier

### Capabilities
- Collision detection
- Gravity
- Force simulation

---

## 9. When to Use Physics

Use only when:
- Part drop simulation
- Collision analysis
- Failure/jam analysis
- Training simulation

Avoid when:
- Deterministic motion (cylinder, conveyor)

---

## 10. Integration with Real Machine (Future)

Architecture:

H7 MCU (IO)
    ↓
Python Control Layer
    ↓
Browser Viewer
    ↓
3D Motion

---

## 11. Key Design Decision

| Area | Decision |
|------|---------|
| Viewer | model-viewer |
| Motion | JavaScript |
| Physics | Not used |
| Complexity | Minimized |
| Future | Expandable |

---

## 12. Guiding Principle

"Build what is needed now. Keep future path open."

---

## 13. Summary

Current:
✅ Lightweight Digital Twin
✅ Browser-based viewer
✅ JS motion control

Future:
🔶 Three.js upgrade
🔶 Physics (optional)
🔶 Full Digital Twin integration

---

## 14. Final Note

This file exists to:

- Prevent future confusion
- Document design decisions
- Provide clear upgrade path

