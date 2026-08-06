# ADR-001: Encoder and Counter Selection for Reel Packing System

## Status
Accepted

## Date
2026-06-23

---

## Context

The system requires accurate tape feeding control for SMD reel packing.

Key requirements:
- Feed pitch: 2 mm / 4 mm
- High repeatability
- Stable operation in industrial environment
- Low development risk in prototype phase

Challenges:
- Incremental encoder does not provide absolute position
- Mechanical variation (slip, vibration, backlash)
- Risk of missed pulses in MCU during early development

---

## Problem Statement

Select a reliable method to:
1. Measure feed distance
2. Control motor stopping position
3. Minimize risk during prototype and commissioning

---

## Options Considered

### Option A: STM32F401 Direct Encoder Interface

**Description:**
- Use STM32 timer (encoder mode / external clock)

**Pros:**
- Low cost (no external hardware)
- Full control flexibility
- High performance (hardware timer)

**Cons:**
- Requires firmware development
- Risk of misconfiguration
- Harder debugging during early stage

---

### Option B: Basic Industrial Counter (CTA4 / TICO / CODIX)

**Description:**
- Use panel counter with pulse input

**Pros:**
- Simple integration
- No firmware required

**Cons:**
- No real quadrature decoding
- Limited speed (~7–10 kHz)
- Reduced flexibility

---

### Option C: Advanced Industrial Counter (RS PRO 20 kHz)

**Description:**
- Use industrial counter with A+B quadrature support

**Pros:**
- Supports A+B encoder (x1 / x2 / x4)
- High input frequency (~20 kHz)
- Built-in filtering and industrial robustness
- Easy debugging (visible count)
- Reduces system risk during prototype

**Cons:**
- Additional hardware cost (~THB 5,000)
- Extra panel space required

---

## Decision

Selected:
**RS PRO Counter (20 kHz, A+B support)**

Reason:
- Provides stable and reliable counting during prototype phase
- Supports quadrature encoder for future upgrade path
- Reduces dependency on firmware at early stage
- Improves observability during machine tuning

---

## System Architecture
Stepper Motor
↓
Incremental Encoder (A+B)
↓
RS PRO Counter
↓
Control Logic
↓
Mechanical Pin Lock (Final Position Reference)
---

## Key Design Principle

Final positioning accuracy is determined by:

Mechanical Pin Lock > Encoder > Counter

Meaning:
- Encoder provides tracking
- Counter processes position
- Mechanical pin ensures true alignment

---

## Consequences

### Positive
- Faster prototype development
- Easier debugging and validation
- Reduced risk of missed pulses
- Clear migration path to MCU

---

### Negative
- Additional BOM cost
- Temporary duplication (counter → MCU in future)

---

## Future Plan (Migration)

### Phase 1: Prototype
- RS PRO Counter handles encoder input

### Phase 2: System Tuning
- Determine:
  - counts per pitch
  - speed limits
  - timing margins

### Phase 3: Production
- Replace RS PRO with STM32F401

Implementation:
TIM External Clock Mode (A-only)
or
Encoder Mode (A+B)

---

## Notes

- Encoder resolution: 200–360 PPR is sufficient
- Recommended mode: x2 (stable), x4 (if signal quality is good)
- Always use mechanical pin as final positioning reference

  


