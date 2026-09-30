"""ตัวรับภาพจากกล้อง HIKROBOT (เช่น MV-CE050-30UM) ผ่าน MVS SDK

ใช้งาน:
    with HikCamera(exposure_us=20000, gain_db=0) as cam:
        img = cam.grab()          # numpy array ขาวดำ (H, W) uint8

ต้องลงโปรแกรม MVS ของ HIKROBOT ก่อน (มีไลบรารี Python ให้ใน MvImport)
และต้องปิดโปรแกรม MVS ตอนรัน เพราะกล้องเปิดได้ทีละโปรแกรม
"""
import ctypes
import os
import sys

import numpy as np

# path ของ MVS SDK แยกตาม OS (หลักพี่เลี้ยง "no OS lock-in") — ตั้งทับได้ด้วยตัวแปร MVS_PY / MVS_RUNTIME
# Linux: ตำแหน่งติดตั้งมาตรฐานของ MVS for Linux คือ /opt/MVS — ยังไม่ได้ทดสอบบน Linux จริง
if sys.platform == "win32":
    _py = r"C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport"
    _rt = r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64"
else:
    _py = "/opt/MVS/Samples/64/Python/MvImport"
    _rt = "/opt/MVS/lib/64"
MVS_PY = os.environ.get("MVS_PY", _py)
MVS_RUNTIME = os.environ.get("MVS_RUNTIME", _rt)

if sys.platform == "win32" and os.path.isdir(MVS_RUNTIME):
    os.add_dll_directory(MVS_RUNTIME)
    os.environ["PATH"] = MVS_RUNTIME + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, MVS_PY)

from MvCameraControl_class import (  # noqa: E402
    MV_ACCESS_Exclusive, MV_CC_DEVICE_INFO, MV_CC_DEVICE_INFO_LIST, MV_FRAME_OUT,
    MV_GIGE_DEVICE, MV_TRIGGER_MODE_OFF, MV_USB_DEVICE, MvCamera, PixelType_Gvsp_Mono8,
)

# Mono12 ให้ระดับสีละเอียดกว่า Mono8 16 เท่า — วัดจริง 23 ก.ย. อ่านรหัสรุ่นถูก 92% เทียบกับ 67%
# (ภาพชิ้นงานมืดและคอนทราสต์ต่ำ ข้อมูลกระจุกอยู่ช่วงแคบ ยิ่งมีขั้นละเอียดยิ่งได้เปรียบ)
PIXEL_FORMATS = {"mono8": (0x01080001, np.uint8), "mono12": (0x01100005, np.uint16)}


class HikCameraError(RuntimeError):
    pass


def _check(ret, what):
    if ret != 0:
        raise HikCameraError(f"{what} ล้มเหลว (รหัส 0x{ret & 0xFFFFFFFF:08X})")


class HikCamera:
    def __init__(self, index=0, exposure_us=None, gain_db=None, pixel_format="mono8"):
        self.index = index
        self.exposure_us = exposure_us
        self.gain_db = gain_db
        if pixel_format not in PIXEL_FORMATS:
            raise HikCameraError(f"รองรับเฉพาะ {list(PIXEL_FORMATS)} แต่ได้ {pixel_format}")
        self.pixel_format = pixel_format
        self.cam = None

    def open(self):
        MvCamera.MV_CC_Initialize()
        devices = MV_CC_DEVICE_INFO_LIST()
        _check(MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE | MV_GIGE_DEVICE, devices), "ค้นหากล้อง")
        if devices.nDeviceNum <= self.index:
            raise HikCameraError("ไม่พบกล้อง: เช็กสาย USB3 และปิดโปรแกรม MVS ก่อน")
        info = ctypes.cast(devices.pDeviceInfo[self.index], ctypes.POINTER(MV_CC_DEVICE_INFO)).contents

        self.cam = MvCamera()
        _check(self.cam.MV_CC_CreateHandle(info), "สร้าง handle")
        _check(self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0), "เปิดกล้อง (โปรแกรมอื่นใช้อยู่หรือเปล่า?)")

        # ต้องสั่งทุกครั้ง: กล้องจำรูปแบบภาพไว้ข้ามการเปิด/ปิดโปรแกรม ถ้าไม่สั่งอาจได้ค่าจากรอบก่อน
        # กับดัก (23 ก.ย.): หลัง OpenDevice ใหม่ๆ กล้องยังไม่ยอมให้เขียน PixelFormat (error 0x80000047)
        # ต้องสั่งเริ่มถ่ายแล้วหยุดหนึ่งรอบก่อน ค่าถึงจะเขียนได้ — พิสูจน์แล้วด้วยการลองทั้งสองลำดับ
        self.cam.MV_CC_StartGrabbing()
        self.cam.MV_CC_StopGrabbing()
        _check(self.cam.MV_CC_SetEnumValue("PixelFormat", PIXEL_FORMATS[self.pixel_format][0]),
               f"ตั้งรูปแบบภาพเป็น {self.pixel_format}")

        self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)  # ถ่ายต่อเนื่อง
        # ปิดตัวจำกัดเฟรมเรต — กล้องจำค่าไว้ข้ามการเปิด/ปิด (28 ก.ย. 2569 เจอค้างที่ 1 fps: ดึงภาพ 1007 ms/เฟรม
        # แอปเฉลี่ย 4 เฟรม = 4 s ต่อผล · VISION รอ ~10 s) · ปิดแล้ว 18 fps = 56 ms/เฟรม · exposure ยาวยังจำกัดเฟรมเรตเองตามปกติ
        self.cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", False)
        if self.exposure_us is not None:
            self.cam.MV_CC_SetEnumValue("ExposureAuto", 0)  # 0 = ปิด auto
            _check(self.cam.MV_CC_SetFloatValue("ExposureTime", float(self.exposure_us)), "ตั้ง exposure")
        if self.gain_db is not None:
            self.cam.MV_CC_SetEnumValue("GainAuto", 0)
            _check(self.cam.MV_CC_SetFloatValue("Gain", float(self.gain_db)), "ตั้ง gain")

        _check(self.cam.MV_CC_StartGrabbing(), "เริ่มถ่าย")
        return self

    def grab(self, timeout_ms=2000):
        """คืนภาพล่าสุดเป็น numpy array ขาวดำ (สูง, กว้าง) — uint8 ถ้า mono8, uint16 ถ้า mono12"""
        frame = MV_FRAME_OUT()
        ctypes.memset(ctypes.byref(frame), 0, ctypes.sizeof(frame))
        _check(self.cam.MV_CC_GetImageBuffer(frame, timeout_ms), "รับภาพ")
        try:
            info = frame.stFrameInfo
            want, dtype = PIXEL_FORMATS[self.pixel_format]
            if info.enPixelType != want:
                raise HikCameraError(f"ขอ {self.pixel_format} แต่กล้องส่ง 0x{info.enPixelType:08X}")
            data = ctypes.string_at(frame.pBufAddr, info.nFrameLen)
            return np.frombuffer(data, dtype).reshape(info.nHeight, info.nWidth).copy()
        finally:
            self.cam.MV_CC_FreeImageBuffer(frame)

    def close(self):
        if self.cam is not None:
            self.cam.MV_CC_StopGrabbing()
            self.cam.MV_CC_CloseDevice()
            self.cam.MV_CC_DestroyHandle()
            self.cam = None
        MvCamera.MV_CC_Finalize()

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
