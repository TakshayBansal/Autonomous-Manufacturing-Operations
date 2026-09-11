"""Northstar factory source simulator. Standard-library only and database blind."""
from __future__ import annotations

import json
import os
import random
import smtplib
import threading
import time
import importlib.util
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
try:
    from lab_engine import LabEngine
except ModuleNotFoundError:  # file-based contract tests load this module outside its service cwd
    _lab_spec=importlib.util.spec_from_file_location("lab_engine",Path(__file__).with_name("lab_engine.py"))
    _lab_module=importlib.util.module_from_spec(_lab_spec); _lab_spec.loader.exec_module(_lab_module)
    LabEngine=_lab_module.LabEngine

TOKEN = os.getenv("FACTORY_SIMULATOR_TOKEN", "northstar-local-simulator-token")
TICK_SECONDS = float(os.getenv("FACTORY_SIMULATOR_TICK_SECONDS", "2"))
STATE_FILE = os.getenv("FACTORY_SIMULATOR_STATE_FILE", "")
CAPABILITIES = {"production", "downtime", "inventory", "supplier_commitments", "quality", "machine_events", "maintenance", "business"}
SCENARIOS = {
    "normal_on_plan", "spindle_temperature_failure", "dimensional_drift",
    "supplier_material_delay", "missing_spare", "line_recovery", "connector_outage",
    "customer_order_surge", "supplier_email_change", "urgent_management_requirement",
    "inbound_vehicle_mismatch", "malformed_source_record", "duplicate_replay",
    "material_quality_hold", "production_counter_reset", "source_conflict",
}
SOURCE_MODEL = [
    {"id":"machine_events","name":"Chakan SCADA / CNC telemetry","protocol":"OPC UA + MQTT","description":"Machine modes, temperatures, vibration and cycle pulses"},
    {"id":"production","name":"Northstar MES","protocol":"REST cursor feed","description":"Work orders, counts and execution state"},
    {"id":"quality","name":"Northstar QMS","protocol":"REST cursor feed","description":"Measurements, defects and inspections"},
    {"id":"inventory","name":"Warehouse Management","protocol":"REST cursor feed","description":"Stock, reservations, staging and receipts"},
    {"id":"supplier_commitments","name":"Supplier Collaboration","protocol":"REST + email","description":"Commitments and dispatch changes"},
    {"id":"maintenance","name":"Northstar CMMS","protocol":"REST cursor feed","description":"Maintenance work and spare state"},
    {"id":"business","name":"ERP and communications","protocol":"REST + SMTP","description":"Plans, orders, logistics and requests"},
]
STREAM_DEFAULTS = {key: True for key in CAPABILITIES}
LAB_PRESETS = [
    {"id":"normal_on_plan","name":"Normal production","description":"Six lines produce counts with normal quality samples.","kind":"steady"},
    {"id":"bearing_heat_ramp","name":"Spindle temperature rising","description":"CNC-01 temperature and vibration rise until V2 detects the condition.","kind":"timeline"},
    {"id":"bore_measurement_drift","name":"Bore dimension drifting","description":"QMS measurements move slowly beyond the upper control limit.","kind":"timeline"},
    {"id":"supplier_commitment_slip","name":"Supplier delivery slipping","description":"Supplier commitment moves beyond the material need time.","kind":"timeline"},
    {"id":"supplier_material_delay","name":"Material shortage","description":"Low usable stock and delayed supply arrive together.","kind":"event"},
    {"id":"missing_spare","name":"Repair waiting for spare","description":"CMMS waits while WMS reports zero bearing stock.","kind":"event"},
    {"id":"customer_order_surge","name":"Urgent customer order","description":"ERP releases additional MES-160 demand.","kind":"event"},
    {"id":"supplier_email_change","name":"Supplier email update","description":"An inbound supplier message revises delivery.","kind":"event"},
    {"id":"inbound_vehicle_mismatch","name":"Gate quantity mismatch","description":"A vehicle arrives with a challan and ASN discrepancy.","kind":"event"},
    {"id":"connector_outage","name":"Connector outage","description":"Source reads fail and freshness becomes stale.","kind":"event"},
    {"id":"line_recovery","name":"Machine recovery","description":"CMMS closes repair and SCADA restores automatic cycle.","kind":"event"},
]
LINE_TARGETS = {"L01": 920, "L02": 840, "L03": 1100, "L04": 960, "L05": 920, "L06": 840}


class Factory:
    def __init__(self, seed: int = 22041072):
        self.seed = seed
        self.lock = threading.RLock()
        self.loop_last_tick_at = None
        self.loop_last_error = None
        self.loop_error_count = 0
        self.lab = LabEngine()
        if not self._load(): self.reset()

    def _load(self):
        if not STATE_FILE or not os.path.exists(STATE_FILE): return False
        try:
            with open(STATE_FILE, encoding="utf-8") as handle: state=json.load(handle)
            self.rng=random.Random(self.seed)
            for _ in range(int(state.get("sequence",0))): self.rng.random()
            self.started_at=datetime.fromisoformat(state["started_at"])
            self.scenario_time=datetime.fromisoformat(state["scenario_time"])
            self.running=bool(state["running"]); self.speed=float(state["speed"]); self.scenario=state["scenario"]
            self.sequence=int(state["sequence"]); self.streams=state["streams"]; self.lines=state["lines"]; self.connector=state["connector"]
            self.run_id=int(state.get("run_id", 1)); self.signals=state.get("signals") or {
                "asset-ns-01-01":{"spindle_temperature_c":61.0,"vibration_mm_s":2.1,"machine_mode":"running"},
                "asset-ns-02-01":{"spindle_temperature_c":59.5,"vibration_mm_s":1.9,"machine_mode":"running"}}
            self.active_timelines=state.get("active_timelines", [])
            self.enabled_streams=state.get("enabled_streams", dict(STREAM_DEFAULTS))
            self.inventory_truth=state.get("inventory_truth",{"RM-ADC12-INGOT":6400.0,"RM-17-4PH-025":480.0})
            self.asset_health=state.get("asset_health",{"asset-ns-01-01":{"health_index":.96,"tool_life":.82},"asset-ns-02-01":{"health_index":.94,"tool_life":.76}})
            return True
        except (OSError,ValueError,KeyError,json.JSONDecodeError): return False

    def _persist(self):
        if not STATE_FILE: return
        directory=os.path.dirname(STATE_FILE)
        if directory: os.makedirs(directory,exist_ok=True)
        temporary=STATE_FILE+".tmp"
        state={"started_at":self.started_at.isoformat(),"scenario_time":self.scenario_time.isoformat(),
            "running":self.running,"speed":self.speed,"scenario":self.scenario,"sequence":self.sequence,
            "run_id":self.run_id,"streams":self.streams,"lines":self.lines,"connector":self.connector,
            "signals":self.signals,"active_timelines":self.active_timelines,"enabled_streams":self.enabled_streams}
        state["inventory_truth"]=self.inventory_truth; state["asset_health"]=self.asset_health
        with open(temporary,"w",encoding="utf-8") as handle: json.dump(state,handle,separators=(",",":"))
        os.replace(temporary,STATE_FILE)
        self.lab.persist()

    def reset(self, publish_normal: bool = False):
        with getattr(self, "lock", threading.RLock()):
            previous_run = getattr(self, "run_id", 0)
            self.rng = random.Random(self.seed)
            self.started_at = datetime.now(timezone.utc)
            self.run_id = previous_run + 1
            self.scenario_time = self.started_at
            self.running, self.speed, self.scenario = True, 1, "normal_on_plan"
            self.sequence = 0
            self.streams = {key: [] for key in CAPABILITIES}
            ist = self.started_at + timedelta(hours=5, minutes=30)
            shift_hour = 6 if 6 <= ist.hour < 14 else 14 if 14 <= ist.hour < 22 else 22
            shift_start = ist.replace(hour=shift_hour, minute=0, second=0, microsecond=0)
            if ist.hour < 6: shift_start -= timedelta(days=1)
            progress = min(max((ist - shift_start).total_seconds() / (8 * 3600), 0), 1)
            offsets = (-.008, .004, -.003, .007, -.005, .002)
            self.lines = {
                code: {"state": "running", "good": round(target * min(max(progress + offsets[index - 1], 0), 1)),
                       "reject": 2 + index, "production_remainder": 0.0}
                for index, (code, target) in enumerate(LINE_TARGETS.items(), 1)
            }
            self.connector = {"state": "fresh", "last_event_at": self.scenario_time.isoformat()}
            self.signals = {"asset-ns-01-01":{"spindle_temperature_c":61.0,"vibration_mm_s":2.1,"machine_mode":"running"},
                            "asset-ns-02-01":{"spindle_temperature_c":59.5,"vibration_mm_s":1.9,"machine_mode":"running"}}
            self.active_timelines = []
            self.enabled_streams = dict(STREAM_DEFAULTS)
            self.inventory_truth={"RM-ADC12-INGOT":6400.0,"RM-17-4PH-025":480.0,"BRG-HSK63-7212":1.0}
            self.asset_health={"asset-ns-01-01":{"health_index":.96,"tool_life":.82},"asset-ns-02-01":{"health_index":.94,"tool_life":.76}}
            # A reset is a new, healthy source run. Publish normal evidence so
            # V2 can close prior inferred machine constraints without deleting
            # their canonical history.
            if publish_normal:
                for asset_id, signals in self.signals.items():
                    self.emit("machine_events", {"event_type":"state","asset_id":asset_id,
                        "work_order_id":"wo-ns-live-01" if asset_id.endswith("01-01") else "wo-ns-live-02",
                        "fault_code":"RECOVERED","message":"Machine healthy after simulation reset"})
                    for _ in range(3):
                        self.emit("machine_events", {"event_type":"signal.sampled","asset_id":asset_id,
                            "work_order_id":"wo-ns-live-01" if asset_id.endswith("01-01") else "wo-ns-live-02",
                            "signals":dict(signals),"source_quality":"good"})
            self._persist()

    def control(self, action: str, speed: int | None = None):
        with self.lock:
            if action == "start": self.running = True
            elif action == "pause": self.running = False
            elif action == "reset": self.reset(publish_normal=True)
            elif action == "speed" and speed in {.1, 1, 5, 10, 60, 300}: self.speed = speed
            else: raise ValueError("Use start, pause, reset, or a supported speed")
            self._persist()

    def inject(self, key: str):
        if key not in SCENARIOS: raise KeyError(key)
        with self.lock:
            self.scenario = key
            if key == "spindle_temperature_failure":
                self.lines["L01"]["state"] = "down"
                self.emit("machine_events", {"event_type": "alarm", "asset_id": "asset-ns-01-01",
                    "work_order_id": "wo-ns-live-01", "fault_code": "SPINDLE-TEMP-HI",
                    "message": "Spindle bearing temperature exceeded 82 C"})
                self.emit("downtime", {"work_order_id": "wo-ns-live-01", "line_id": "line-ns-01",
                    "asset_id": "asset-ns-01-01", "started_at": (self.scenario_time-timedelta(minutes=22)).isoformat(),
                    "category": "breakdown", "reason": "Spindle bearing temperature high", "planned": False})
                self.emit("maintenance", {"asset_id": "asset-ns-01-01", "external_reference": f"CMMS-{self.sequence+1:06}",
                    "title": "Inspect spindle bearing and lubrication circuit", "status": "acknowledged",
                    "owner_user_id": "usr-ns-07", "spare_code": "BRG-HSK63-7212", "spare_available": True,
                    "started_at": self.scenario_time.isoformat()})
            elif key == "dimensional_drift":
                self.emit("quality", {"work_order_id": "wo-ns-live-02", "line_id": "line-ns-02",
                    "asset_id": "asset-ns-02-01", "event_type": "measurement", "inspected_quantity": 40,
                    "rejected_quantity": 9, "defect_code": "BORE-OVERSIZE", "measurement_name": "caliper_bore_mm",
                    "measurement_value": 42.084, "lower_control_limit": 41.95, "upper_control_limit": 42.05,
                    "material_lot_id": "LOT-BC410-260813-04", "severity": "high"})
            elif key == "supplier_material_delay":
                self.emit("supplier_commitments", {"work_order_id": "wo-ns-live-03", "material_code": "RM-17-4PH-025",
                    "supplier_id": "sup-ns-precision-forgings", "committed_quantity": 220,
                    "committed_delivery_at": (self.scenario_time+timedelta(hours=18)).isoformat(),
                    "acknowledged": True, "reliability_score": .71, "status": "open",
                    "message_subject": "Revised delivery commitment for PO NS-PO-2608-114"})
                self.emit("inventory", {"material_code": "RM-17-4PH-025", "on_hand_quantity": 35,
                    "reserved_for_other_orders": 12, "quality_hold_quantity": 0,
                    "observed_at": self.scenario_time.isoformat(), "reason": "supplier_delay"})
            elif key == "missing_spare":
                self.emit("maintenance", {"asset_id": "asset-ns-01-01", "external_reference": f"CMMS-{self.sequence+1:06}",
                    "title": "Replace spindle bearing cartridge", "status": "waiting_for_spare", "owner_user_id": "usr-ns-07",
                    "spare_code": "BRG-HSK63-7212", "spare_available": False, "started_at": self.scenario_time.isoformat()})
                self.emit("inventory", {"material_code": "BRG-HSK63-7212", "on_hand_quantity": 0,
                    "reserved_for_other_orders": 0, "quality_hold_quantity": 0, "observed_at": self.scenario_time.isoformat()})
            elif key == "line_recovery":
                self.lines["L01"]["state"] = "running"
                self.emit("maintenance", {"asset_id": "asset-ns-01-01", "external_reference": "CMMS-RECOVERY-001",
                    "title": "Spindle bearing replacement", "status": "completed", "owner_user_id": "usr-ns-07",
                    "spare_code": "BRG-HSK63-7212", "spare_available": True,
                    "started_at": (self.scenario_time-timedelta(minutes=34)).isoformat(), "completed_at": self.scenario_time.isoformat(),
                    "resolution": "Bearing cartridge replaced; vibration and temperature verified"})
                self.emit("machine_events", {"event_type": "state", "asset_id": "asset-ns-01-01",
                    "work_order_id": "wo-ns-live-01", "fault_code": "RECOVERED", "message": "Machine returned to automatic cycle"})
            elif key == "normal_on_plan":
                for line in self.lines.values(): line["state"] = "running"
                self.emit("inventory", {"material_code": "RM-ADC12-INGOT", "on_hand_quantity": 6400,
                    "reserved_for_other_orders": 900, "quality_hold_quantity": 0, "observed_at": self.scenario_time.isoformat()})
            elif key == "customer_order_surge":
                self.emit("business", {"event_type":"customer.order","order_number":f"NS-WO-RUSH-{self.sequence+1:05}",
                    "external_reference":f"SAP-SO-{self.sequence+1:07}","line_id":"line-ns-04",
                    "shift_id":self._active_shift_id(),"product_code":"MES-160","product_name":"Motor End Shield MES-160",
                    "target_quantity":480,"planned_start_at":(self.scenario_time+timedelta(hours=3)).isoformat(),
                    "planned_end_at":(self.scenario_time+timedelta(hours=11)).isoformat()})
            elif key == "supplier_email_change":
                self.emit("business", {"event_type":"supplier.mail","supplier_id":"sup-ns-precision-forgings",
                    "external_message_id":f"mail-{self.sequence+1}@sahyadri-forgings.local",
                    "sender":"dispatch@sahyadri-forgings.local","recipient":"snehal.patil@northstar-mobility.local",
                    "subject":"Delivery commitment revision — NS-PO-2608-114",
                    "body_preview":"Heat-treatment release is delayed. Revised vehicle reporting is 18:30 IST."})
            elif key == "urgent_management_requirement":
                self.emit("business", {"event_type":"management.requirement","title":"Prepare capacity response for accelerated GH-220 demand",
                    "owner_role":"production_manager","severity":"high","priority":"urgent","production_impact":"direct",
                    "requested_outcome":"Confirm line capacity, material cover and overtime decision.",
                    "due_at":(self.scenario_time+timedelta(minutes=45)).isoformat()})
            elif key == "inbound_vehicle_mismatch":
                self.emit("business", {"event_type":"logistics.arrival","title":"Resolve challan quantity mismatch for MH14-KL-4821",
                    "owner_role":"gate_operator","severity":"high","priority":"high","production_impact":"indirect",
                    "requested_outcome":"Verify ASN, challan and physical package count before gate clearance.",
                    "due_at":(self.scenario_time+timedelta(minutes=20)).isoformat()})
            elif key == "malformed_source_record":
                self.emit("quality", {"event_type":"measurement","measurement_name":"bore_diameter_mm"})
            elif key == "duplicate_replay":
                candidates=[row for rows in self.streams.values() for row in rows]
                if candidates:
                    original=dict(candidates[-1]); self.sequence+=1; original["cursor"]=str(self.sequence)
                    self.streams[original["capability"]].append(original)
            elif key == "material_quality_hold":
                self.emit("quality", {"work_order_id":"wo-ns-live-03","line_id":"line-ns-03","event_type":"hold",
                    "material_lot_id":"LOT-17-4PH-260814-07","inspected_quantity":220,"rejected_quantity":0,
                    "reason":"Metallurgical certificate pending"})
                self.emit("inventory", {"material_code":"RM-17-4PH-025","on_hand_quantity":260,
                    "reserved_for_other_orders":0,"quality_hold_quantity":220,"observed_at":self.scenario_time.isoformat()})
            elif key == "production_counter_reset":
                line=self.lines["L01"]
                self.emit("production", {"work_order_id":"wo-ns-live-01","line_id":"line-ns-01",
                    "good_increment":0,"good_quantity":0,"reject_quantity":line["reject"],"cumulative_good":0,
                    "state":"running","counter_epoch":self.run_id+1,"source_note":"PLC counter restarted"})
            elif key == "source_conflict":
                self.signals["asset-ns-01-01"]["machine_mode"]="down"
                self.emit("machine_events", {"event_type":"state","asset_id":"asset-ns-01-01",
                    "work_order_id":"wo-ns-live-01","machine_mode":"down","alarm_code":"SERVO-410"})
                self.emit("production", {"work_order_id":"wo-ns-live-01","line_id":"line-ns-01","good_increment":0,
                    "good_quantity":self.lines["L01"]["good"],"reject_quantity":self.lines["L01"]["reject"],
                    "cumulative_good":self.lines["L01"]["good"],"state":"running","source_note":"MES state delayed"})
            self._persist()

    def emit(self, capability: str, payload: dict):
        if not self.enabled_streams.get(capability, True): return
        self.sequence += 1
        run=self.lab.current(); chaos=((run or {}).get("configuration") or {}).get("chaos",{})
        occurred=self.scenario_time+timedelta(seconds=float(chaos.get("clock_skew_seconds",0)))
        row = {"cursor": str(self.sequence), "event_id": f"NS-R{self.run_id:06}-{self.sequence:012}", "occurred_at": occurred.isoformat(),
               "capability": capability, "payload": payload,
               "lab":{"run_id":run["id"],"scenario_id":run["scenario_id"],"virtual_time":self.scenario_time.isoformat()} if run else None}
        lost=self.rng.random()*100 < float(chaos.get("event_loss_percent",0))
        if lost:
            row["delivery_status"]="dropped_by_chaos"
        elif self.rng.random()*100 < float(chaos.get("out_of_order_percent",0)) and self.streams[capability]:
            row["delivery_status"]="out_of_order"; self.streams[capability].insert(max(len(self.streams[capability])-1,0),row)
        else: self.streams[capability].append(row)
        if not lost and self.rng.random()*100 < float(chaos.get("duplicate_percent",0)):
            duplicate=dict(row); self.sequence+=1; duplicate["cursor"]=str(self.sequence); duplicate["delivery_status"]="duplicate"
            self.streams[capability].append(duplicate)
        self.streams[capability] = self.streams[capability][-10000:]
        self.lab.record_event(row)

    def start_lab_run(self, scenario_id: str, seed: int | None = None):
        definition=self.lab.scenario(scenario_id)
        if not definition: raise ValueError("Unknown versioned scenario")
        self.reset()
        run=self.lab.create_run(scenario_id,self.scenario_time.isoformat(),seed)
        preset=definition["preset"]
        if preset in {"bearing_heat_ramp","bore_measurement_drift","supplier_commitment_slip"}: self.start_timeline(preset)
        else: self.inject(preset)
        # A new run always starts in continuous mode. This is deliberately
        # explicit because a prior manual step leaves the factory paused.
        self.running=True; self.speed=run["speed"]; self._persist(); return run

    def lab_control(self, action: str, value=None):
        if action=="step":
            self.running=True; self.tick(10 / self.speed); self.running=False; self._persist()
            return self.lab.control("pause",self.scenario_time.isoformat())
        if action=="reset":
            current=self.lab.current()
            return self.start_lab_run(current["scenario_id"],current["seed"]) if current else None
        mapped={"pause":"pause","resume":"start","speed":"speed"}
        if action in mapped: self.control(mapped[action],value)
        return self.lab.control(action,self.scenario_time.isoformat(),value)

    def send_supplier_email(self, payload: dict):
        """Cross the real SMTP boundary, then expose the same raw mail to the connector fixture."""
        sender=str(payload.get("sender") or "dispatch@sahyadri-forgings.local")
        recipient=str(payload.get("recipient") or "snehal.patil@northstar-mobility.local")
        subject=str(payload.get("subject") or "Commitment update — NS-PO-2608-114")
        body=str(payload.get("body") or "Heat treatment is delayed. We expect dispatch tomorrow evening.")
        message=EmailMessage(); message["From"]=sender; message["To"]=recipient; message["Subject"]=subject; message.set_content(body)
        document_type=str(payload.get("attachment_type") or "none")
        if document_type=="csv": message.add_attachment(b"PO,Material,Quantity,Commitment\nNS-PO-2608-114,RM-17-4PH-025,220,2026-08-17\n",maintype="text",subtype="csv",filename="dispatch_commitment.csv")
        elif document_type=="pdf":
            pdf=b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
            message.add_attachment(pdf,maintype="application",subtype="pdf",filename="supplier_commitment.pdf")
        with smtplib.SMTP(os.getenv("LAB_SMTP_HOST","mailpit"),int(os.getenv("LAB_SMTP_PORT","1025")),timeout=5) as client: client.send_message(message)
        external_id=f"mail-{self.run_id}-{self.sequence+1}@sahyadri-forgings.local"
        self.emit("business", {"event_type":"supplier.mail","supplier_id":"sup-ns-precision-forgings",
            "external_message_id":external_id,"sender":sender,"recipient":recipient,"subject":subject,
            "body_preview":body[:500],"attachment_names":[part.get_filename() for part in message.iter_attachments()]})
        self.lab.sources["email"]["events_emitted"]+=1; self.lab.sources["email"]["last_event_at"]=self.scenario_time.isoformat()
        self.lab.sources["documents"]["events_emitted"]+=sum(1 for _ in message.iter_attachments()); self.lab.persist()
        return {"external_message_id":external_id,"smtp":"accepted","attachments":[part.get_filename() for part in message.iter_attachments()]}

    def publish_signals(self, payload: dict):
        with self.lock:
            asset_id = str(payload.get("asset_id") or "")
            if asset_id not in self.signals: raise ValueError("Unknown allowlisted asset")
            allowed = {key: payload[key] for key in ("spindle_temperature_c","vibration_mm_s","machine_mode") if key in payload}
            self.signals[asset_id].update(allowed)
            self.emit("machine_events", {"event_type":"signal.sampled","asset_id":asset_id,
                "work_order_id":"wo-ns-live-01" if asset_id.endswith("01-01") else "wo-ns-live-02",
                "signals":dict(self.signals[asset_id]),"source_quality":"good"})
            self._persist()

    def start_timeline(self, timeline_id: str):
        definitions={"bearing_heat_ramp":24,"bore_measurement_drift":20,"supplier_commitment_slip":3}
        if timeline_id not in definitions: raise ValueError("Unknown factual timeline")
        with self.lock:
            self.active_timelines=[row for row in self.active_timelines if row["id"] != timeline_id]
            self.active_timelines.append({"id":timeline_id,"step":0,"total_steps":definitions[timeline_id]})
            self._persist()

    def set_stream(self, capability: str, enabled: bool):
        if capability not in CAPABILITIES: raise ValueError("Unknown source stream")
        with self.lock:
            self.enabled_streams[capability] = bool(enabled)
            self._persist()

    def run_preset(self, preset_id: str):
        if preset_id in {"bearing_heat_ramp", "bore_measurement_drift", "supplier_commitment_slip"}:
            return self.start_timeline(preset_id)
        return self.inject(preset_id)

    def apply_recovery_strategy(self, strategy_type: str):
        """React with source-system facts; never emit a GenuineGigs outcome label."""
        with self.lock:
            if strategy_type in {"repair_asset", "repair_plus_overtime", "recover_line_rate"}:
                self.lines["L01"]["state"]="running"
                self.signals["asset-ns-01-01"].update(spindle_temperature_c=66.0,vibration_mm_s=2.8,machine_mode="running")
                self.emit("maintenance", {"asset_id":"asset-ns-01-01","external_reference":f"CMMS-REC-{self.sequence+1:06}",
                    "title":"Restore spindle assembly","status":"completed","owner_user_id":"usr-ns-07",
                    "spare_code":"BRG-HSK63-7212","spare_available":True,
                    "started_at":(self.scenario_time-timedelta(minutes=35)).isoformat(),"completed_at":self.scenario_time.isoformat(),
                    "resolution":"Bearing and lubrication circuit restored; guarded run accepted"})
                for _ in range(3):
                    self.emit("machine_events", {"event_type":"signal.sampled","asset_id":"asset-ns-01-01",
                        "work_order_id":"wo-ns-live-01","signals":dict(self.signals["asset-ns-01-01"]),"source_quality":"good"})
            elif strategy_type == "reroute_work_order":
                self.emit("business", {"event_type":"management.requirement","title":"Release compatible quantity to Line 4",
                    "owner_role":"production_manager","severity":"high","priority":"urgent","production_impact":"direct",
                    "requested_outcome":"Verify tooling, material and first-off quality before alternate-line release.",
                    "due_at":(self.scenario_time+timedelta(minutes=20)).isoformat()})
                self.lines["L04"]["state"]="running"
                self.emit("quality", {"work_order_id":"wo-ns-live-04","line_id":"line-ns-04","event_type":"inspection",
                    "inspected_quantity":5,"rejected_quantity":0,"defect_code":None,"severity":"normal"})
            elif strategy_type == "supplier_expedite":
                self.emit("supplier_commitments", {"work_order_id":"wo-ns-live-03","material_code":"RM-17-4PH-025",
                    "supplier_id":"sup-ns-precision-forgings","committed_quantity":260,
                    "committed_delivery_at":(self.scenario_time+timedelta(hours=2)).isoformat(),
                    "acknowledged":True,"reliability_score":.82,"status":"open"})
            elif strategy_type == "alternate_material":
                self.emit("quality", {"work_order_id":"wo-ns-live-03","line_id":"line-ns-03","event_type":"release",
                    "inspected_quantity":1,"rejected_quantity":0,"material_lot_id":"LOT-17-4PH-ALT-01","severity":"normal"})
                self.emit("inventory", {"material_code":"RM-17-4PH-025","on_hand_quantity":420,
                    "reserved_for_other_orders":20,"quality_hold_quantity":0,"observed_at":self.scenario_time.isoformat(),
                    "reason":"approved_alternate_lot_released"})
            elif strategy_type == "resequence_production":
                self.emit("business", {"event_type":"management.requirement","title":"Publish material-ready production sequence",
                    "owner_role":"production_manager","severity":"high","priority":"high","production_impact":"direct",
                    "requested_outcome":"Move the ready work order forward without losing protected customer demand.",
                    "due_at":(self.scenario_time+timedelta(minutes=15)).isoformat()})
            elif strategy_type in {"contain_and_adjust", "switch_material_lot", "inspect_100_percent"}:
                for _ in range(3):
                    self.emit("quality", {"work_order_id":"wo-ns-live-02","line_id":"line-ns-02","event_type":"measurement",
                        "inspected_quantity":10,"rejected_quantity":0,"measurement_name":"caliper_bore_mm",
                        "measurement_value":42.0,"lower_control_limit":41.95,"upper_control_limit":42.05,
                        "material_lot_id":"LOT-BC410-RELEASED"})
            else: raise ValueError("Unsupported simulated recovery strategy")
            self._persist()

    def control_timeline(self, timeline_id: str, action: str):
        with self.lock:
            row=next((item for item in self.active_timelines if item["id"] == timeline_id),None)
            if not row: raise ValueError("Timeline is not active")
            if action == "pause": row["paused"] = True
            elif action == "start": row["paused"] = False
            elif action == "stop": self.active_timelines.remove(row)
            else: raise ValueError("Use start, pause, or stop")
            self._persist()

    def _advance_timelines(self):
        remaining=[]
        for row in self.active_timelines:
            if row.get("paused"): remaining.append(row); continue
            row["step"] += 1; step=row["step"]
            if row["id"] == "bearing_heat_ramp":
                temperature=round(61 + step, 1); vibration=round(2.1 + step * .14, 2)
                self.signals["asset-ns-01-01"].update(spindle_temperature_c=temperature,vibration_mm_s=vibration)
                self.asset_health["asset-ns-01-01"]["health_index"]=max(.96-step*.027,.2)
                self.emit("machine_events", {"event_type":"signal.sampled","asset_id":"asset-ns-01-01",
                    "work_order_id":"wo-ns-live-01","signals":dict(self.signals["asset-ns-01-01"]),"source_quality":"good"})
            elif row["id"] == "bore_measurement_drift":
                self.emit("quality", {"work_order_id":"wo-ns-live-02","line_id":"line-ns-02","event_type":"measurement",
                    "inspected_quantity":5,"rejected_quantity":0,"measurement_name":"caliper_bore_mm",
                    "measurement_value":round(42.0 + step*.003,3),"lower_control_limit":41.95,"upper_control_limit":42.05})
            elif row["id"] == "supplier_commitment_slip" and step == 3:
                self.emit("supplier_commitments", {"work_order_id":"wo-ns-live-03","material_code":"RM-17-4PH-025",
                    "supplier_id":"sup-ns-precision-forgings","committed_quantity":220,
                    "committed_delivery_at":(self.scenario_time+timedelta(hours=18)).isoformat(),"acknowledged":True,"status":"open"})
            if step < row["total_steps"]: remaining.append(row)
        self.active_timelines=remaining

    def tick(self, wall_seconds: float | None = None):
        with self.lock:
            if not self.running: return
            scenario_seconds = self.speed * (TICK_SECONDS if wall_seconds is None else wall_seconds)
            self.scenario_time += timedelta(seconds=scenario_seconds)
            self._advance_timelines()
            if self.scenario == "connector_outage":
                self.connector["state"] = "stale"; self._persist(); return
            self.connector = {"state": "fresh", "last_event_at": self.scenario_time.isoformat()}
            for code, line in self.lines.items():
                if self.scenario == "spindle_temperature_failure" and code == "L01":
                    if line["state"] != "down": self.emit("downtime", {"line": code, "asset": "CNC-01-01", "state": "started", "reason": "Spindle bearing temperature high"})
                    line["state"] = "down"; continue
                if line["state"]=="starved":
                    index=int(code[1:]); self.emit("production", {"work_order_id":f"wo-ns-live-{index:02}","line_id":f"line-ns-{index:02}",
                        "good_increment":0,"good_quantity":line["good"],"reject_quantity":line["reject"],"cumulative_good":line["good"],"state":"starved"})
                    continue
                # Pace cumulative output against the eight-hour shift target.
                exact_increment = LINE_TARGETS[code] * scenario_seconds / (8 * 60 * 60)
                accumulated = float(line.get("production_remainder", 0)) + exact_increment
                increment = int(accumulated)
                line["production_remainder"] = accumulated - increment
                line["good"] = min(line["good"] + increment, LINE_TARGETS[code])
                if code=="L01": self.inventory_truth["RM-ADC12-INGOT"]=max(self.inventory_truth["RM-ADC12-INGOT"]-increment*1.8,0)
                elif code=="L03": self.inventory_truth["RM-17-4PH-025"]=max(self.inventory_truth["RM-17-4PH-025"]-increment*.42,0)
                if code=="L03" and self.inventory_truth["RM-17-4PH-025"]<=0: line["state"]="starved"
                if line["good"] >= LINE_TARGETS[code]: line["state"] = "complete"
                index = int(code[1:])
                self.emit("production", {"work_order_id": f"wo-ns-live-{index:02}", "line_id": f"line-ns-{index:02}",
                    "good_increment": increment, "good_quantity": line["good"], "reject_quantity": line["reject"],
                    "cumulative_good": line["good"], "state": line["state"]})
            if self.sequence % 17 == 0:
                wear=self.asset_health["asset-ns-02-01"]["tool_life"]
                self.emit("quality", {"work_order_id": "wo-ns-live-02", "line_id": "line-ns-02", "event_type": "measurement",
                    "inspected_quantity": 10, "rejected_quantity": 0, "measurement_name": "caliper_bore_mm",
                    "measurement_value": round(self.rng.gauss(42.0+(1-wear)*.012, .018), 3), "lower_control_limit": 41.95,
                    "upper_control_limit": 42.05, "material_lot_id": "LOT-BC410-LIVE"})
            if self.sequence % 10 < 2:
                self.emit("inventory", {"material_code":"RM-17-4PH-025","on_hand_quantity":round(self.inventory_truth["RM-17-4PH-025"],2),
                    "reserved_for_other_orders":12,"quality_hold_quantity":0,"observed_at":self.scenario_time.isoformat(),"reason":"bom_consumption_snapshot"})
            self._persist()

    def state(self):
        with self.lock:
            return {"running": self.running, "speed": self.speed, "scenario": self.scenario,
                    "scenario_time": self.scenario_time.isoformat(), "sequence": self.sequence,
                    "run_id":self.run_id,"lines": self.lines, "connector": self.connector,
                    "signals":self.signals,"active_timelines":self.active_timelines,
                    "enabled_streams":self.enabled_streams,"inventory_truth":self.inventory_truth,"asset_health":self.asset_health,
                    "available_scenarios": sorted(SCENARIOS),
                    "loop_health":{"status":"error" if self.loop_last_error else "healthy",
                        "last_tick_at":self.loop_last_tick_at,"last_error":self.loop_last_error,
                        "error_count":self.loop_error_count,"wall_interval_seconds":TICK_SECONDS}}

    def _active_shift_id(self):
        local=self.scenario_time+timedelta(hours=5,minutes=30)
        code="A" if 6<=local.hour<14 else "B" if 14<=local.hour<22 else "C"
        shift_day=local.date() if local.hour>=6 else (local-timedelta(days=1)).date()
        return f"shift-ns-{shift_day:%Y%m%d}-{code}"


factory = Factory()


def loop():
    while True:
        try:
            factory.tick()
            factory.loop_last_tick_at=datetime.now(timezone.utc).isoformat()
            factory.loop_last_error=None
        except Exception as exc:  # keep the test bench alive and expose the fault
            factory.loop_error_count += 1
            factory.loop_last_error=f"{type(exc).__name__}: {exc}"
        time.sleep(TICK_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def response(self, status, payload):
        body = json.dumps(payload).encode(); self.send_response(status)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def authorized(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health": return self.response(200, {"status": "ok"})
        if not self.authorized(): return self.response(401, {"detail": "Invalid simulator token"})
        if parsed.path == "/lab/v2/live":
            self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.send_header("Cache-Control","no-cache"); self.send_header("X-Accel-Buffering","no"); self.end_headers()
            cursor=factory.sequence
            try:
                while True:
                    events=[]; run=factory.lab.current()
                    if run: events=[row for row in run["events"] if int(row["id"].rsplit("-",1)[-1])>cursor]
                    for event in events:
                        cursor=int(event["id"].rsplit("-",1)[-1]); data=json.dumps(event,separators=(",",":"))
                        self.wfile.write(f"id: {event['id']}\nevent: factory.event\ndata: {data}\n\n".encode())
                    if not events: self.wfile.write(f"event: heartbeat\ndata: {json.dumps({'virtual_time':factory.scenario_time.isoformat(),'sequence':factory.sequence})}\n\n".encode())
                    self.wfile.flush(); time.sleep(1)
            except (BrokenPipeError,ConnectionResetError): return
        if parsed.path == "/sim/v1/state": return self.response(200, factory.state())
        if parsed.path == "/lab/v1/state": return self.response(200, factory.state())
        if parsed.path == "/lab/v1/model": return self.response(200, {"sources":[{**row,"status":factory.connector["state"],"enabled":factory.enabled_streams.get(row["id"],True)} for row in SOURCE_MODEL],"presets":LAB_PRESETS})
        if parsed.path == "/lab/v1/sources": return self.response(200, {"sources":[{**row,"status":factory.connector["state"]} for row in SOURCE_MODEL]})
        if parsed.path == "/lab/v1/ground-truth": return self.response(200, {"run_id":factory.run_id,"active_experiments":factory.active_timelines})
        if parsed.path == "/lab/v2/summary": return self.response(200,{**factory.lab.summary(),"factory":factory.state()})
        if parsed.path == "/lab/v2/scenarios": return self.response(200,{"scenarios":factory.lab.scenarios()})
        if parsed.path == "/lab/v2/runs": return self.response(200,{"runs":[{k:r.get(k) for k in ("id","scenario_id","scenario_name","scenario_version","seed","status","started_at","virtual_time","speed","parent_run_id","result")} for r in reversed(factory.lab.runs)]})
        if parsed.path == "/lab/v2/sources": return self.response(200,{"sources":list(factory.lab.sources.values())})
        if parsed.path == "/erp/materials": return self.response(200,{"items":[{"material":"RM-ADC12-INGOT","plant":"NSPM-CHK","uom":"KG","changed_at":factory.scenario_time.isoformat()},{"material":"RM-17-4PH-025","plant":"NSPM-CHK","uom":"KG","changed_at":factory.scenario_time.isoformat()}],"fidelity":"contract_fixture"})
        if parsed.path == "/erp/suppliers": return self.response(200,{"items":[{"vendor":"NS-V0047","name":"Sahyadri Precision Forgings","status":"ACTIVE"}],"fidelity":"contract_fixture"})
        if parsed.path == "/erp/purchase-orders": return self.response(200,{"items":[{"purchase_order":"NS-PO-2608-114","vendor":"NS-V0047","material":"RM-17-4PH-025","quantity":260,"plant":"NSPM-CHK"}]})
        if parsed.path == "/erp/production-orders": return self.response(200,{"items":[{"order":f"wo-ns-live-{i:02}","work_center":f"L{i:02}","status":factory.lines[f'L{i:02}']["state"]} for i in range(1,7)]})
        if parsed.path == "/mes/operations": return self.response(200,{"items":[{"line":code,"state":row["state"],"good_count":row["good"],"reject_count":row["reject"]} for code,row in factory.lines.items()]})
        if parsed.path == "/wms/inventory": return self.response(200,{"items":[row["payload"] for row in factory.streams["inventory"][-50:]]})
        if parsed.path == "/qms/measurements": return self.response(200,{"items":[row["payload"] for row in factory.streams["quality"][-50:]]})
        if parsed.path == "/cmms/work-orders": return self.response(200,{"items":[row["payload"] for row in factory.streams["maintenance"][-50:]]})
        parts=parsed.path.strip("/").split("/")
        if len(parts)>=4 and parts[:3]==["lab","v2","runs"]:
            run=next((row for row in factory.lab.runs if row["id"]==parts[3]),None)
            if not run: return self.response(404,{"detail":"Run not found"})
            if len(parts)==4: return self.response(200,run)
            if parts[4]=="timeline": return self.response(200,{"run_id":run["id"],"events":run["events"],"injections":run["injections"]})
            if parts[4]=="assertions": return self.response(200,{"run_id":run["id"],"assertions":run["assertions"],"result":run["result"]})
        if parsed.path.startswith("/sim/v1/streams/"):
            if factory.connector["state"] == "stale":
                return self.response(503, {"detail": "Simulated connector outage"})
            capability = parsed.path.rsplit("/", 1)[-1]
            if capability not in CAPABILITIES: return self.response(404, {"detail": "Unknown capability"})
            cursor = int(parse_qs(parsed.query).get("cursor", ["0"])[0])
            if cursor > factory.sequence: cursor = 0
            rows = [row for row in factory.streams[capability] if int(row["cursor"]) > cursor]
            return self.response(200, {"records": rows[:500], "next_cursor": rows[min(len(rows), 500)-1]["cursor"] if rows else str(cursor)})
        self.response(404, {"detail": "Not found"})

    def do_POST(self):
        if not self.authorized(): return self.response(401, {"detail": "Invalid simulator token"})
        size = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(size) or b"{}")
        try:
            if self.path == "/sim/v1/control": factory.control(payload.get("action", ""), payload.get("speed")); return self.response(200, factory.state())
            if self.path == "/lab/v1/control": factory.control(payload.get("action", ""), payload.get("speed")); return self.response(200, factory.state())
            if self.path == "/lab/v2/runs":
                run=factory.start_lab_run(str(payload.get("scenario_id") or ""),payload.get("seed")); return self.response(201,run)
            if self.path == "/lab/v2/scenarios/validate": return self.response(200,factory.lab.validate_scenario(payload))
            if self.path == "/lab/v2/scenarios/save": return self.response(201,factory.lab.save_scenario(payload))
            if self.path.startswith("/lab/v2/runs/"):
                parts=self.path.strip("/").split("/"); run_id=parts[3]
                if run_id!=factory.lab.current_run_id and parts[-1] not in {"replay"}: raise ValueError("Run is not active")
                action=parts[4] if len(parts)>4 else ""
                if action in {"pause","resume","step","reset","speed"}:
                    return self.response(200,factory.lab_control(action,payload.get("speed") or payload.get("value")))
                if action=="fork": return self.response(201,factory.lab.fork(str(payload.get("event_id") or ""),factory.scenario_time.isoformat()))
                if action=="replay": return self.response(201,factory.lab.replay(run_id,str(payload.get("mode") or "exact")))
                if action=="inject":
                    row=factory.lab.inject(str(payload.get("type") or "manual"),str(payload.get("target") or ""),payload.get("parameters") or {},factory.scenario_time.isoformat())
                    params=payload.get("parameters") or {}; injection=str(payload.get("type") or "")
                    if injection=="machine_signal": factory.publish_signals({"asset_id":payload.get("target"),**params})
                    elif injection=="scenario": factory.run_preset(str(params.get("preset") or payload.get("target")))
                    elif injection=="source_toggle": factory.set_stream(str(payload.get("target")),bool(params.get("enabled")))
                    return self.response(202,row)
                if action=="chaos": return self.response(200,factory.lab.chaos(payload))
                if action=="assertions": return self.response(200,{"assertions":factory.lab.set_assertions(payload.get("updates") or [])})
            if self.path == "/lab/v2/email/send": return self.response(202,factory.send_supplier_email(payload))
            if self.path.startswith("/lab/v1/timelines/"):
                timeline_id,action=self.path.split("/")[-2:]
                if action == "start" and not any(row["id"] == timeline_id for row in factory.active_timelines): factory.start_timeline(timeline_id)
                else: factory.control_timeline(timeline_id,action)
                return self.response(202, factory.state())
            if self.path.startswith("/lab/v1/presets/"):
                factory.run_preset(self.path.rsplit("/",1)[-1]); return self.response(202,factory.state())
            if self.path.startswith("/lab/v1/streams/"):
                capability=self.path.rsplit("/",1)[-1]; factory.set_stream(capability,bool(payload.get("enabled")))
                return self.response(200,factory.state())
            if self.path.startswith("/lab/v2/sources/"):
                parts=self.path.strip("/").split("/"); source_id=parts[3]
                source=factory.lab.sources.get(source_id)
                if not source: raise ValueError("Unknown source system")
                if parts[-1]=="control":
                    source["enabled"]=bool(payload.get("enabled",True)); source["status"]="connected" if source["enabled"] else "paused"
                    source["latency_ms"]=max(0,min(int(payload.get("latency_ms",source["latency_ms"])),5000))
                    factory.lab.persist(); return self.response(200,source)
                if parts[-1]=="fault":
                    fault=str(payload.get("fault") or ""); enabled=bool(payload.get("enabled",True))
                    source["faults"]=list(dict.fromkeys(([ *source["faults"],fault] if enabled else [x for x in source["faults"] if x!=fault])))
                    source["status"]="degraded" if source["faults"] else "connected"; factory.lab.persist(); return self.response(200,source)
            if self.path.startswith("/lab/v1/sources/") and self.path.endswith("/events"):
                capability=self.path.split("/")[-2]
                if capability not in CAPABILITIES: raise ValueError("Unknown source domain")
                factory.emit(capability,payload); factory._persist(); return self.response(202,{"accepted":True,"sequence":factory.sequence})
            if self.path.startswith("/sim/v1/scenarios/"): factory.inject(self.path.rsplit("/", 1)[-1]); return self.response(202, factory.state())
            if self.path == "/sim/v1/recovery-strategies": factory.apply_recovery_strategy(str(payload.get("strategy_type") or "")); return self.response(202, factory.state())
        except (ValueError, KeyError) as exc: return self.response(422, {"detail": str(exc)})
        self.response(404, {"detail": "Not found"})

    def do_PATCH(self):
        if not self.authorized(): return self.response(401, {"detail": "Invalid simulator token"})
        size=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(size) or b"{}")
        try:
            if self.path == "/lab/v1/sources/ot-scada/signals":
                factory.publish_signals(payload); return self.response(202,factory.state())
        except ValueError as exc: return self.response(422,{"detail":str(exc)})
        self.response(404,{"detail":"Not found"})

    def log_message(self, *_args): pass


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
