# SMD Reel Packing FSM (Simple)

## INIT
- Go to READY

## READY
- Wait Start
  - Start → INDEX

## INDEX
- Feed Carrier Tape
- Go to CHECK_INDEX

## CHECK_INDEX
- Position OK?
  - YES → LOAD_PART
  - NO → ALARM

## LOAD_PART
- Place Component
- Go to VISION

## VISION
- Check Part
  - OK → FEED_COVER
  - NG → ALARM

## FEED_COVER
- Feed Cover Tape
- Go to CHECK_TEMP

## CHECK_TEMP
- Temperature Ready?
  - YES → SEAL
  - NO → Wait

## SEAL
- Heat + Pressure
- Go to SEAL_CHECK

## SEAL_CHECK
- Seal OK?
  - YES → ROLL
  - NO → ALARM

## ROLL
- Wind Reel
- Go to COUNT_CHECK

## COUNT_CHECK
- Count done?
  - YES → STOP
  - NO → INDEX

## STOP
- Go to READY

## ALARM
- Stop Machine
- Reset → INIT
 
