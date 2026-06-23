import asyncio
import aiocoap.resource as resource
import aiocoap
import socket
import json
import urllib.request


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Could not determine IP"


class TemperatureSensor:
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude
        self.temperature = None

    def read(self):
        return self.temperature

    def update(self, value):
        self.temperature = value


def fetch_temperature(latitude, longitude):
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&current=temperature_2m"
    )

    with urllib.request.urlopen(url) as response:
        data = json.load(response)

    return data["current"]["temperature_2m"]


async def update_temperature(sensor):
    while True:
        try:
            temp = await asyncio.to_thread(
                fetch_temperature,
                sensor.latitude,
                sensor.longitude
            )
            sensor.update(temp)
            print(f"[SERVER] Updated temperature: {temp}°C")
        except Exception as e:
            print(f"[SERVER] Error updating temperature: {e}")

        await asyncio.sleep(150)  # update every 2.5 minutes


class TemperatureResource(resource.Resource):
    def __init__(self, sensor):
        super().__init__()
        self.sensor = sensor

    async def render_get(self, request):
        print(f"[SERVER] GET request from {request.remote.hostinfo}")
        temperature = self.sensor.read()

        if temperature is None:
            payload = b"No temperature available"
        else:
            payload = str(temperature).encode("utf-8")

        return aiocoap.Message(payload=payload)


def create_resource_tree(sensor):
    root = resource.Site()
    root.add_resource(["sensor", "temperature"], TemperatureResource(sensor))
    return root


async def main():
    # ── Location: Cagliari, Sardinia ─────────────────────────────────────────
    latitude  = 39.2238
    longitude =  9.1217

    sensor = TemperatureSensor(latitude, longitude)

    # Fetch initial temperature before starting the server
    try:
        first_temp = await asyncio.to_thread(fetch_temperature, latitude, longitude)
        sensor.update(first_temp)
        print(f"[SERVER] Initial temperature: {first_temp}°C")
    except Exception as e:
        print(f"[SERVER] Initial fetch error: {e}")

    # Start background task that refreshes the temperature every 2.5 minutes
    asyncio.create_task(update_temperature(sensor))

    root = create_resource_tree(sensor)

    # ── Bind to the iPhone hotspot interface ─────────────────────────────────
    # When your Mac/PC joins the iPhone hotspot, it gets an IP like 172.20.10.x.
    # This call auto-detects that IP by seeing which interface can route to
    # the internet through the hotspot.
    local_ip = get_ip()

    print("\n=== CoAP Temperature Server ===")
    print(f"Location  : Cagliari, Sardinia")
    print(f"Server IP : {local_ip}")
    print(f"Port      : 5683")
    print(f"Resource  : coap://{local_ip}:5683/sensor/temperature")
    print("================================")
    print("→ Enter this IP in the NodeMCU sketch as SERVER_IP")
    print("→ Make sure the NodeMCU is connected to the same iPhone hotspot\n")

    await aiocoap.Context.create_server_context(root, bind=(local_ip, 5683))
    print("Waiting for requests from NodeMCU ...")

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SERVER] Server shutdown by user")
    except Exception as e:
        print(f"\n[SERVER] Server error: {e}")