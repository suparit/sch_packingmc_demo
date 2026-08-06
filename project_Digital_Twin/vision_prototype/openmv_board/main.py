import sensor, image, time, ustruct, pyb

sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE) # ขาวดำความเร็วสูง
sensor.set_framesize(sensor.QVGA)      # ส่งภาพเต็มเฟรม 320x240 เสมอ
sensor.set_auto_gain(True)
sensor.set_auto_exposure(True)
sensor.skip_frames(time=2000)

usb = pyb.USB_VCP()

print("Full Frame Serial Stream Active...")

while True:
    img = sensor.snapshot()

    # บีบอัดภาพเต็มเฟรม 320x240 ส่งออกไปเลย ไม่ต้องตัดแบ่งบนบอร์ดแล้ว
    img.compress(quality=50)

    # ส่งขนาดและไบนารีภาพเต็มเฟรม เข้าพอร์ต PC
    usb.send(ustruct.pack("<I", img.size()))
    usb.send(img)

    time.sleep_ms(20)
