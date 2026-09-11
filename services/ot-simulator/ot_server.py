"""Real MQTT publisher and OPC UA server backed by Factory Lab truth."""
import asyncio, json, os, urllib.request
from asyncua import Server
import paho.mqtt.client as mqtt

FACTORY=os.getenv("FACTORY_SIMULATOR_URL","http://factory-simulator:8090")
TOKEN=os.getenv("FACTORY_SIMULATOR_TOKEN","northstar-local-simulator-token")
BROKER=os.getenv("MQTT_HOST","mqtt")

def truth():
    request=urllib.request.Request(FACTORY+"/lab/v1/state",headers={"Authorization":f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request,timeout=3) as response: return json.loads(response.read())

async def main():
    server=Server(); await server.init(); server.set_endpoint("opc.tcp://0.0.0.0:4840/northstar/")
    uri="urn:northstar:chakan:cnc"; namespace=await server.register_namespace(uri)
    machine=await (await (await server.nodes.objects.add_object(namespace,"Plant")).add_object(namespace,"Machining")).add_object(namespace,"CNC-01-01")
    nodes={name:await machine.add_variable(namespace,name,initial) for name,initial in
           (("State","running"),("PartCount",0),("CycleTime",36.0),("SpindleTemperature",61.0),("Vibration",2.1),("AlarmCode",""),("ToolLife",.82))}
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="northstar-cnc-01")
    client.will_set("spBv1.0/NSPM/DDATA/CNC-01-01",json.dumps({"state":"offline"}),qos=1,retain=True)
    client.connect(BROKER,1883,60); client.loop_start()
    client.publish("spBv1.0/NSPM/NBIRTH/CHAKAN",json.dumps({"state":"online","device":"CNC-01-01"}),qos=1,retain=True)
    async with server:
        while True:
            try:
                state=truth(); signal=state["signals"]["asset-ns-01-01"]; line=state["lines"]["L01"]
                values={"State":signal["machine_mode"],"PartCount":line["good"],"CycleTime":36.0,
                    "SpindleTemperature":signal["spindle_temperature_c"],"Vibration":signal["vibration_mm_s"],
                    "AlarmCode":"" if signal["machine_mode"]=="running" else "SPINDLE-TEMP-HI","ToolLife":.82}
                for key,value in values.items(): await nodes[key].write_value(value)
                payload={"device":"CNC-01-01","asset_id":"asset-ns-01-01","virtual_time":state["scenario_time"],
                    "metrics":{"machine_mode":values["State"],"part_count":values["PartCount"],
                    "cycle_time_seconds":values["CycleTime"],"spindle_temperature_c":values["SpindleTemperature"],
                    "vibration_mm_s":values["Vibration"],"alarm_code":values["AlarmCode"],"tool_life":values["ToolLife"]}}
                client.publish("spBv1.0/NSPM/DDATA/CNC-01-01",json.dumps(payload),qos=1,retain=True)
            except Exception: pass
            await asyncio.sleep(1)

asyncio.run(main())
