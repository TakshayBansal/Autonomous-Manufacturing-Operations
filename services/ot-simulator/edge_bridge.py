"""Outbound-only MQTT/OPC lab bridge into the signed GenuineGigs edge API."""
import json, os, queue, time, urllib.request
from uuid import uuid4
import paho.mqtt.client as mqtt

API=os.getenv("GENUINEGIGS_API_URL","http://api:8000")
BROKER=os.getenv("MQTT_HOST","mqtt"); pending=queue.Queue()

def connected(client,_userdata,_flags,reason_code,_properties):
    if reason_code==0: client.subscribe("spBv1.0/NSPM/DDATA/+",qos=1)
def message(_client,_userdata,msg):
    try: pending.put(json.loads(msg.payload))
    except (ValueError,UnicodeDecodeError): pass
def deliver(source):
    metrics=source.get("metrics",{}); alarm=metrics.get("alarm_code")
    event={"message_id":f"mqtt-{uuid4()}","event_type":"machine.alarm" if alarm else "machine.state",
        "asset_id":source.get("asset_id","asset-ns-01-01"),"source_timestamp":source.get("virtual_time"),
        "payload":{"protocol":"mqtt","topic":"spBv1.0/NSPM/DDATA/CNC-01-01","signals":metrics,
                   "fault_code":alarm,"message":f"MQTT device alarm {alarm}" if alarm else "MQTT state update"}}
    request=urllib.request.Request(API+"/api/v2/edge/events",data=json.dumps(event).encode(),method="POST",headers={
        "Content-Type":"application/json","X-Edge-Identity":"northstar-edge-chakan-sha256",
        "X-Config-Signature":"northstar-edge-config-v1","Idempotency-Key":event["message_id"]})
    try: urllib.request.urlopen(request,timeout=5).close()
    except Exception: pass

client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="genuinegigs-lab-edge")
client.on_connect=connected; client.on_message=message
while True:
    try: client.connect(BROKER,1883,60); break
    except OSError: time.sleep(2)
client.loop_start()
while True:
    deliver(pending.get())
