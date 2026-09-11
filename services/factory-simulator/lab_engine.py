"""Deterministic Developer Lab run, scenario, chaos, assertion and replay model.

This module is deliberately database-blind. It owns simulated-world truth and
lab-only expectations; GenuineGigs receives only source-native stream records.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from uuid import uuid4

LAB_STATE_FILE = os.getenv("FACTORY_LAB_STATE_FILE", "")

SCENARIOS = [
    {"id":"healthy_shift","version":1,"code":"S01","name":"Healthy stable shift","category":"baseline","golden":True,
     "description":"Normal source timing, production, quality and supply. Measures false positives.","preset":"normal_on_plan",
     "assertions":[("ingestion","source records accepted"),("detection","no new high-severity deviation"),("recovery","no unnecessary Recovery Case")]},
    {"id":"gradual_machine_degradation","version":1,"code":"S02","name":"Gradual machine degradation","category":"machine","golden":True,
     "description":"Temperature and vibration rise as cycle stability deteriorates.","preset":"bearing_heat_ramp",
     "assertions":[("ingestion","machine samples accepted"),("state","machine health becomes WATCH or FAULT"),("detection","maintenance deviation created"),("recovery","Recovery Case opens with repair and reroute options")]},
    {"id":"sudden_machine_fault","version":1,"code":"S03","name":"Sudden machine fault","category":"machine","golden":True,
     "description":"PLC alarm and stopped counts precede delayed CMMS acknowledgement.","preset":"spindle_temperature_failure",
     "assertions":[("detection","downtime deviation created"),("execution","maintenance action assigned"),("verification","not recovered before healthy evidence")]},
    {"id":"supplier_commitment_slip","version":1,"code":"S04","name":"Supplier commitment slip","category":"material","golden":True,
     "description":"A dated commitment moves beyond need-by while ERP stock remains low.","preset":"supplier_commitment_slip",
     "assertions":[("state","material readiness becomes AT_RISK or BLOCKED"),("recovery","expedite and resequence considered"),("impact","material exposure calculated")]},
    {"id":"quality_spc_drift","version":1,"code":"S05","name":"Quality SPC drift","category":"quality","golden":True,
     "description":"A sequence of raw bore measurements crosses the control limit.","preset":"bore_measurement_drift",
     "assertions":[("ingestion","measurements preserved"),("detection","quality deviation created"),("recovery","containment strategy available")]},
    {"id":"material_quality_hold","version":1,"code":"S06","name":"Material quality hold","category":"cross_functional","golden":True,
     "description":"QMS disposition removes physically present stock from usable inventory.","preset":"material_quality_hold",
     "assertions":[("state","quality HOLD and material risk remain separate"),("execution","quality owns release decision"),("recovery","alternate lot considered")]},
    {"id":"production_counter_reset","version":1,"code":"S07","name":"Production counter reset","category":"data_quality","golden":True,
     "description":"MES cumulative counter restarts without producing negative output.","preset":"production_counter_reset",
     "assertions":[("ingestion","counter reset is accepted once"),("state","actual quantity remains monotonic"),("impact","forecast remains bounded")]},
    {"id":"source_conflict","version":1,"code":"S08","name":"Source authority conflict","category":"data_quality","golden":True,
     "description":"OT reports stopped while lagging MES reports running and ERP plan remains unchanged.","preset":"source_conflict",
     "assertions":[("state","source disagreement is visible"),("detection","OT authority drives execution state"),("ingestion","no source fact is silently discarded")]},
    {"id":"connectivity_outage","version":1,"code":"S09","name":"Connectivity outage and replay","category":"chaos","golden":True,
     "description":"Source goes stale, buffers events, reconnects and replays without double counting.","preset":"connector_outage",
     "assertions":[("state","source freshness becomes stale"),("ingestion","replay is idempotent"),("detection","stale warning is not a machine failure")]},
    {"id":"recovery_branch_comparison","version":1,"code":"S10","name":"Repair versus reroute","category":"recovery","golden":True,
     "description":"Fork the same fault and compare repair, reset and reroute outcomes.","preset":"spindle_temperature_failure",
     "branches":["repair_asset","reset_controller","reroute_work_order","do_nothing"],
     "assertions":[("recovery","multiple feasible strategies generated"),("verification","outcome follows source evidence"),("learning","strategy outcome stored for future ranking")]},
]

SOURCE_DEFINITIONS = [
    ("erp","Virtual ERP","HTTP REST","contract","production plans, orders, costs and supplier master"),
    ("mes","Virtual MES","HTTP cursor","semantic","work order execution, counts, scrap and changeover"),
    ("wms","Virtual WMS / Stores","HTTP cursor","semantic","inventory, reservations, staging, receipts and spares"),
    ("qms","Virtual QMS","HTTP cursor","semantic","measurements, defects, holds, NCR and release"),
    ("cmms","Virtual CMMS","HTTP cursor","semantic","maintenance requests, acknowledgement, parts and completion"),
    ("email","Supplier Mail","SMTP","protocol","threads, ambiguous commitments and attachments"),
    ("documents","Document Generator","SMTP / files","contract","PDF, XLSX and CSV extraction fixtures"),
    ("mqtt","IIoT MQTT","MQTT 3.1.1","protocol","birth, state, counts, alarms and telemetry"),
    ("opcua","CNC OPC UA","OPC UA","protocol","machine hierarchy and current tag values"),
]

DEFAULT_CHAOS = {"network_latency_ms":0,"event_loss_percent":0,"duplicate_percent":0,
    "out_of_order_percent":0,"clock_skew_seconds":0,"api_error_percent":0,
    "erp_lag_seconds":0,"mes_lag_seconds":0,"qms_lag_seconds":0,"email_lag_seconds":0}


class LabEngine:
    def __init__(self):
        self.runs=[]; self.current_run_id=None; self.selected_time=None; self.custom_scenarios=[]
        self.sources={key:{"id":key,"name":name,"protocol":protocol,"fidelity":fidelity,
            "description":description,"enabled":True,"status":"connected","latency_ms":0,
            "events_emitted":0,"last_event_at":None,"faults":[]} for key,name,protocol,fidelity,description in SOURCE_DEFINITIONS}
        self._load()

    def _load(self):
        if not LAB_STATE_FILE: return
        try:
            with open(LAB_STATE_FILE,encoding="utf-8") as handle:
                raw=json.load(handle)
            self.runs=raw.get("runs",[])[-40:]; self.current_run_id=raw.get("current_run_id")
            self.sources.update(raw.get("sources",{})); self.selected_time=raw.get("selected_time"); self.custom_scenarios=raw.get("custom_scenarios",[])
        except (OSError,ValueError,json.JSONDecodeError): pass

    def persist(self):
        if not LAB_STATE_FILE: return
        directory=os.path.dirname(LAB_STATE_FILE)
        if directory: os.makedirs(directory,exist_ok=True)
        temp=LAB_STATE_FILE+".tmp"
        with open(temp,"w",encoding="utf-8") as handle:
            json.dump({"runs":self.runs[-40:],"current_run_id":self.current_run_id,
                       "sources":self.sources,"selected_time":self.selected_time,"custom_scenarios":self.custom_scenarios},handle,default=str,separators=(",",":"))
        os.replace(temp,LAB_STATE_FILE)

    def scenario(self, scenario_id):
        return next((row for row in [*SCENARIOS,*self.custom_scenarios] if row["id"]==scenario_id),None)

    def scenarios(self): return [*SCENARIOS,*self.custom_scenarios]

    def validate_scenario(self, definition):
        errors=[]
        for field in ("id","version","name","preset","assertions"):
            if not definition.get(field): errors.append(f"{field} is required")
        if definition.get("preset") not in {"normal_on_plan","bearing_heat_ramp","bore_measurement_drift","supplier_commitment_slip",*list({row["preset"] for row in SCENARIOS})}:
            errors.append("preset must map to a factual simulator behavior")
        if not isinstance(definition.get("assertions",[]),list): errors.append("assertions must be a list")
        return {"valid":not errors,"errors":errors,"normalized":definition if not errors else None}

    def save_scenario(self, definition):
        result=self.validate_scenario(definition)
        if not result["valid"]: raise ValueError("; ".join(result["errors"]))
        row=deepcopy(definition); row.setdefault("code",f"C{len(self.custom_scenarios)+1:02}"); row.setdefault("category","custom"); row.setdefault("golden",False); row.setdefault("description","Authored Developer Lab scenario")
        row["assertions"]=[tuple(item) for item in row["assertions"]]
        self.custom_scenarios=[item for item in self.custom_scenarios if not (item["id"]==row["id"] and item["version"]==row["version"])]+[row]
        self.persist(); return row

    def current(self):
        return next((row for row in self.runs if row["id"]==self.current_run_id),None)

    def create_run(self, scenario_id, virtual_time, seed=None, parent=None, fork_event_id=None):
        definition=self.scenario(scenario_id)
        if not definition: raise ValueError("Unknown versioned scenario")
        if self.current() and self.current()["status"]=="running": self.current()["status"]="superseded"
        run={"id":f"R-{uuid4().hex[:10].upper()}","scenario_id":scenario_id,"scenario_version":definition["version"],
             "scenario_name":definition["name"],"seed":int(seed if seed is not None else 8124),
             "started_at":datetime.now(timezone.utc).isoformat(),"virtual_started_at":virtual_time,"virtual_time":virtual_time,
             "completed_at":None,"speed":1,"status":"running","configuration":{"chaos":deepcopy(DEFAULT_CHAOS),"scale":"pilot"},
             "parent_run_id":parent,"fork_event_id":fork_event_id,"events":[],"injections":[],"choices":[],
             "assertions":[{"id":f"{definition['code']}-A{index:02}","category":category,"description":description,
                            "status":"waiting","expected":description,"observed":None,"evaluated_at":None,"details":{}}
                           for index,(category,description) in enumerate(definition["assertions"],1)],
             "result":{"assertions_passed":0,"assertions_failed":0,"assertions_waiting":len(definition["assertions"]),
                       "false_positive_count":0,"false_negative_count":0,"mean_detection_latency_ms":None,
                       "recovery_success":None,"verified_value":0}}
        self.runs.append(run); self.current_run_id=run["id"]; self.persist(); return run

    def control(self, action, virtual_time, value=None):
        run=self.current()
        if not run: raise ValueError("Start a scenario run first")
        if action in {"pause","resume","stop"}: run["status"]={"pause":"paused","resume":"running","stop":"completed"}[action]
        elif action=="speed":
            if float(value) not in {.1,1,5,10,60,300}: raise ValueError("Unsupported virtual speed")
            run["speed"]=float(value)
        elif action=="select_time": self.selected_time=str(value)
        else: raise ValueError("Unknown run control")
        run["virtual_time"]=virtual_time
        if action=="stop": run["completed_at"]=datetime.now(timezone.utc).isoformat()
        self.persist(); return run

    def record_event(self, event, source=None, protocol=None):
        run=self.current()
        if not run: return
        capability=event.get("capability")
        source=source or {"production":"mes","downtime":"mes","inventory":"wms","supplier_commitments":"erp",
                          "quality":"qms","machine_events":"mqtt","maintenance":"cmms","business":"erp"}.get(capability,"erp")
        source_row=self.sources.get(source)
        if source_row:
            source_row["events_emitted"]+=1; source_row["last_event_at"]=event.get("occurred_at")
        lab_event={"id":event["event_id"],"run_id":run["id"],"scenario_id":run["scenario_id"],
            "virtual_time":event.get("occurred_at"),"source_system":source,"protocol":protocol or (source_row or {}).get("protocol","HTTP"),
            "capability":capability,"event_type":event.get("payload",{}).get("event_type") or capability,
            "summary":self._summary(event),"payload":event.get("payload",{}),"trace_id":f"lab:{run['id']}:{event['event_id']}",
            "ingestion_status":event.get("delivery_status","emitted")}
        run["events"].append(lab_event); run["events"]=run["events"][-5000:]; run["virtual_time"]=event.get("occurred_at")

    @staticmethod
    def _summary(event):
        payload=event.get("payload",{}); capability=event.get("capability","")
        if capability=="machine_events": return f"{payload.get('asset_id','asset')} {payload.get('event_type','signal')}"
        if capability=="production": return f"{payload.get('line_id','line')} cumulative good {payload.get('good_quantity','—')}"
        if capability=="quality": return f"{payload.get('measurement_name') or payload.get('event_type','quality')} {payload.get('measurement_value','')}".strip()
        if capability=="inventory": return f"{payload.get('material_code','material')} on hand {payload.get('on_hand_quantity','—')}"
        return str(payload.get("title") or payload.get("message_subject") or payload.get("status") or capability)

    def inject(self, injection_type, target, parameters, virtual_time, initiated_by="developer"):
        run=self.current()
        if not run: raise ValueError("Start a scenario run first")
        row={"id":f"I-{uuid4().hex[:10].upper()}","run_id":run["id"],"virtual_time":virtual_time,
             "type":injection_type,"target":target,"parameters":parameters,"initiated_by":initiated_by}
        run["injections"].append(row); self.persist(); return row

    def chaos(self, config):
        run=self.current()
        if not run: raise ValueError("Start a scenario run first")
        merged={**DEFAULT_CHAOS,**{key:value for key,value in config.items() if key in DEFAULT_CHAOS}}
        for key in ("event_loss_percent","duplicate_percent","out_of_order_percent","api_error_percent"):
            merged[key]=min(max(float(merged[key]),0),20)
        merged["network_latency_ms"]=min(max(int(merged["network_latency_ms"]),0),5000)
        run["configuration"]["chaos"]=merged; self.persist(); return merged

    def fork(self, event_id, virtual_time):
        parent=self.current()
        if not parent: raise ValueError("No current run")
        child=self.create_run(parent["scenario_id"],virtual_time,parent["seed"],parent["id"],event_id)
        child["events"]=deepcopy([row for row in parent["events"] if row["id"]<=event_id])
        child["injections"]=deepcopy(parent["injections"]); self.persist(); return child

    def replay(self, run_id, mode="exact"):
        original=next((row for row in self.runs if row["id"]==run_id),None)
        if not original: raise ValueError("Run not found")
        replay=self.create_run(original["scenario_id"],original["virtual_started_at"],original["seed"],original["id"])
        replay["configuration"]=deepcopy(original["configuration"]); replay["replay_mode"]=mode
        replay["replay_source_events"]=deepcopy(original["events"]); self.persist(); return replay

    def set_assertions(self, updates):
        run=self.current()
        if not run: return None
        by_id={row["id"]:row for row in run["assertions"]}
        for update in updates:
            if update.get("id") in by_id: by_id[update["id"]].update(update)
        statuses=[row["status"] for row in run["assertions"]]
        run["result"].update(assertions_passed=statuses.count("passed"),assertions_failed=statuses.count("failed"),
                             assertions_waiting=statuses.count("waiting"))
        self.persist(); return run["assertions"]

    def summary(self):
        run=self.current()
        return {"current_run":{key:run.get(key) for key in ("id","scenario_id","scenario_version","scenario_name","seed","started_at","virtual_started_at","virtual_time","speed","status","configuration","parent_run_id")} if run else None,
                "sources":list(self.sources.values()),"scenario_count":len(self.scenarios()),"golden_count":sum(row["golden"] for row in self.scenarios()),
                "selected_time":self.selected_time}
