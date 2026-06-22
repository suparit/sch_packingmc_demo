# CAD - SMD Reel Packing Machine

## Purpose
Store 3D models for Digital Twin visualization and mechanical reference.

This folder is used for:
- Web-based 3D viewer (GitHub Pages)
- Local simulation (motion / testing)
- Training and demonstration

---

## Structure

- export/ → 3D models
  - .step → engineering reference
  - .glb  → web viewer / Digital Twin

- preview/ → screenshots (optional)

- docs/ → mechanism / description (optional)

- viewer.html → online viewer (GitHub Pages)

- viewer_local.html → local test + motion control

---

## Workflow

1. Design in Fusion 360

2. Prepare model in Blender
   - Reduce polygon (Decimate)
   - Apply modifier ✅
   - Reduce texture size
   - Keep correct position (origin)

3. Export
   - .step (engineering use)
   - .glb (viewer / web)

4. Upload to this repository

---

## Usage

### 1. Online Viewer (GitHub Pages)

Open in browser:
https://suparit.github.io/sch_packingmc_demo/cad/viewer.html

✅ Use for:
- Demo
- Mobile view
- Sharing

---

### 2. Local Test (Animation / Simulation)

Run local server:

```bash
python -m http.server 8080

Open:
http://localhost:8080/cad/viewer_local.html

✅ Use for:

Motion testing
Debug
Cylinder / actuator simulation


Model Strategy (IMPORTANT)
Models can be separated by function:

machine.glb → main structure (static)
cylinder.glb → moving part

All parts must:

Share same coordinate system ✅
Export without moving position ✅


Motion Concept
Simple approach for Digital Twin:

Use JavaScript
Move object using:

translateX / translateY



Example:
JavaScriptcylinder.style.transform = "translateX(50px)";Show more lines

Notes

GitHub Pages is static → no backend
Local test is used for motion control
Future:

FSM (machine logic)
Modbus → Web → Model sync




---



