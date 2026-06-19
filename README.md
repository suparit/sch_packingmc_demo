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
 
