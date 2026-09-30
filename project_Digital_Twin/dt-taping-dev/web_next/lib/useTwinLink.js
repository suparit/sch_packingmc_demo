'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { EMPTY_SYSTEM } from './twin.js';
import { getDemoMachine } from './demoMachine.js';

// ต่อ gateway ทาง WebSocket 8765 (protocol.md ข้อ 3–4, 8)
// · มี gateway → LIVE: ปุ่มส่ง action เข้า gateway จริง ACK กลับมาทาง onmessage
// · ไม่มี gateway → DEMO: ปุ่มสั่งตัวจำลองในเบราว์เซอร์ (lib/demoMachine.js) ACK ตอบทันที
// เปลี่ยนปลายทางด้วย ?ws=ws://192.168.x.x:8765 · ปิดโหมดจำลองด้วย ?demo=0
// หรือกล่อง "เชื่อมกับ gateway" (กดป้ายสถานะมุมขวาบน /twin) — ใช้เฉพาะหน้านี้ ไม่จำข้าม reload ตั้งใจ:
// ถ้าจำ ที่อยู่ที่เคยลองพิมพ์จะชนะ START.bat → เว็บค้าง DEMO วันทดสอบโดยไม่รู้ตัว

export const DEFAULT_WS_URL = 'ws://127.0.0.1:8765';

const FLUSH_MS = 100; // gateway ส่งทุก 50 ms — วาด React 10 ครั้ง/วิ พอสำหรับตัวเลข
const HISTORY_MS = 500;
const HISTORY_LEN = 90; // ≈ 45 วินาที
const DEMO_AFTER_MS = 1500;
const ACK_TYPES = new Set(['MODE_ACK', 'NEXT_ACK', 'DECISION_ACK', 'SYNC_ACK']); // SYNC_ACK = ปุ่ม Sync บอร์ด (gateway 01_DigitalTwin)

function params() {
  if (typeof window === 'undefined') return new URLSearchParams();
  return new URLSearchParams(window.location.search);
}

function wsUrl(picked) {
  if (picked) return picked; // พิมพ์ในกล่องเชื่อม — ชนะ ?ws=
  const q = params().get('ws');
  if (q) return q;
  return `ws://${window.location.hostname || 'localhost'}:8765`;
}

export function useTwinLink() {
  const [system, setSystem] = useState(EMPTY_SYSTEM);
  const [link, setLink] = useState({ status: 'connecting', url: '' });
  const [history, setHistory] = useState({ temp: [], pieces: [] });
  const [events, setEvents] = useState([]); // ACK + ข้อความจากฝั่งเรา สำหรับแสดง toast
  const [records, setRecords] = useState(null); // แถว HISTORY_RESPONSE ล่าสุด (null = ยังไม่เคยได้)
  // ประวัติ ALARM พร้อมสาเหตุ (คีย์ alarms ของ HISTORY_RESPONSE · gateway 01_DigitalTwin 27 ก.ย. 2569) · null = gateway ไม่ส่ง
  const [alarms, setAlarms] = useState(null);

  const latest = useRef(EMPTY_SYSTEM);
  const liveAt = useRef(0);
  const wsRef = useRef(null);
  const demoRef = useRef(null);
  const sourceRef = useRef('none');
  const hist = useRef({ temp: [], pieces: [] });
  const eventId = useRef(0);
  const [attempt, setAttempt] = useState(0); // เพิ่มทีละ 1 = ปิดสายเดิม ต่อปลายทางใหม่
  // false = ผู้ใช้กด "เลิกเชื่อม" — ไม่ต่อ gateway ใช้ตัวจำลองอย่างเดียว
  // ไม่จำข้าม reload ตั้งใจ: เปิดจาก START.bat ต้องต่อ gateway เองเสมอ ไม่งั้นหน้าเครื่องงงว่าทำไมเป็น DEMO
  const [enabled, setEnabled] = useState(true);
  const pickedUrl = useRef('');

  const pushEvent = useCallback((ev) => {
    eventId.current += 1;
    const item = { id: eventId.current, at: Date.now(), ...ev };
    setEvents((list) => [...list.slice(-5), item]);
  }, []);

  useEffect(() => {
    let ws;
    let retry;
    let closed = false;
    const url = wsUrl(pickedUrl.current);
    // เลิกเชื่อม = เข้าตัวจำลองทันที ไม่ต้องรอ DEMO_AFTER_MS
    const bootAt = performance.now() - (enabled ? 0 : DEMO_AFTER_MS);
    // ต่อใหม่ (กด "เชื่อม") → ล้างค่าจากสายเดิม ไม่ให้ป้ายค้าง LIVE ด้วยข้อมูลเก่า
    liveAt.current = 0;
    sourceRef.current = 'none';
    latest.current = EMPTY_SYSTEM;
    demoRef.current = params().get('demo') === '0' ? null : getDemoMachine();
    setLink({ status: 'connecting', url, enabled });

    const connect = () => {
      if (!enabled) return;
      try {
        ws = new WebSocket(url);
      } catch {
        retry = setTimeout(connect, 2000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => ws.send(JSON.stringify({ action: 'GET_STATE' }));
      ws.onmessage = (ev) => {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        // ❗ ข้อมูลอยู่ใต้ .system — ไม่มีคีย์ชื่อ state ในระบบ (protocol.md ข้อ 3)
        if (msg?.type === 'LIVE_SYNC' && msg.system) {
          latest.current = { ...EMPTY_SYSTEM, ...msg.system };
          liveAt.current = performance.now();
        } else if (msg?.type === 'HISTORY_RESPONSE') {
          setRecords(Array.isArray(msg.data) ? msg.data : []);
          setAlarms(Array.isArray(msg.alarms) ? msg.alarms : null);
        } else if (ACK_TYPES.has(msg?.type)) {
          pushEvent({ kind: 'ack', ...msg });
        }
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    };
    connect();

    const flush = setInterval(() => {
      const now = performance.now();
      const live = liveAt.current > 0 && now - liveAt.current < 1000;
      const demo = demoRef.current;
      const source = live ? 'gateway' : demo && now - bootAt > DEMO_AFTER_MS ? 'demo' : 'none';
      if (source !== sourceRef.current) {
        // สลับแหล่งข้อมูล → ล้างกราฟ ไม่ให้ค่าจำลองปนค่าจริง
        hist.current = { temp: [], pieces: [] };
        sourceRef.current = source;
        setLink({
          status: source === 'gateway' ? 'live' : source === 'demo' ? 'demo' : demo && enabled ? 'connecting' : 'offline',
          url,
          enabled,
        });
      }
      if (source === 'demo') latest.current = demo.tick(now);
      setSystem(latest.current);
    }, FLUSH_MS);

    const sample = setInterval(() => {
      const s = latest.current;
      if (s === EMPTY_SYSTEM) return;
      const push = (arr, v) => {
        arr.push(v);
        if (arr.length > HISTORY_LEN) arr.shift();
      };
      push(hist.current.temp, Number(s.current_temp) || 0);
      push(hist.current.pieces, Number(s.pieces_count) || 0);
      setHistory({ temp: [...hist.current.temp], pieces: [...hist.current.pieces] });
    }, HISTORY_MS);

    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(flush);
      clearInterval(sample);
      ws?.close();
    };
  }, [pushEvent, attempt, enabled]);

  // กล่อง "เชื่อมกับ gateway" — ค่าว่าง = กลับไปใช้ค่าตั้งต้น (เครื่องเดียวกับหน้าเว็บ :8765)
  const connectTo = useCallback((url) => {
    pickedUrl.current = url;
    setEnabled(true);
    setAttempt((n) => n + 1);
  }, []);

  const disconnect = useCallback(() => setEnabled(false), []);

  // ส่งคำสั่ง — รูปแบบ {"action": ..., ...} ตาม protocol.md ข้อ 4
  const send = useCallback(
    (action, payload = {}) => {
      if (sourceRef.current === 'gateway') {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          pushEvent({ kind: 'local', ok: false, text: 'สายหลุด — ส่งคำสั่งไม่ได้' });
          return false;
        }
        ws.send(JSON.stringify({ action, ...payload }));
        return true;
      }
      if (sourceRef.current === 'demo' && demoRef.current) {
        const ack = demoRef.current.command(action, payload);
        latest.current = demoRef.current.tick(performance.now());
        setSystem(latest.current);
        if (ack?.type === 'HISTORY_RESPONSE') {
          setRecords(ack.data);
          setAlarms(Array.isArray(ack.alarms) ? ack.alarms : null);
        }
        else if (ack) pushEvent({ kind: 'ack', ...ack });
        return true;
      }
      pushEvent({ kind: 'local', ok: false, text: 'ยังไม่ได้เชื่อมต่อ' });
      return false;
    },
    [pushEvent],
  );

  const setCameraAuto = useCallback((on) => {
    if (demoRef.current) demoRef.current.opts.cameraAuto = on;
  }, []);

  return { system, link, history, events, send, setCameraAuto, records, alarms, connectTo, disconnect };
}
