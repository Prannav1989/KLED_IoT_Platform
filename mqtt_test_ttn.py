import paho.mqtt.client as mqtt

# --- Hardcoded TTN Credentials ---
BROKER = "au1.cloud.thethings.network"
PORT = 8883
USERNAME = "redico@ttn"   # Application ID + @ttn
PASSWORD = "NNSXS.K7FSYVKQ7XBCTXLBQTCC4G2IVMNA6DSVCSMF3PQ.CTSOTMOJLHHC43HRAIUH3I4QD6FH2C5AFYODTLVLBDRQNQHJDJ2Q"  # <-- replace with your API key

# --- Callback functions ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Connected successfully to TTN")
        # Subscribe to all topics
        client.subscribe("#")
    else:
        print(f"❌ Failed to connect. Return code: {rc}")

def on_message(self, client, userdata, msg, config):
    print(f"📡 Topic: {msg.topic}\nMessage: {msg.payload.decode()}\n")

def on_disconnect(client, userdata, rc):
    print("⚠️ Disconnected:", rc)

# --- Setup MQTT Client ---
client = mqtt.Client()
client.username_pw_set(USERNAME.strip(), PASSWORD.strip())

# TTN requires TLS
client.tls_set()

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

print(f"Connecting to {BROKER}:{PORT} as {USERNAME} ...")
client.connect(BROKER, PORT, keepalive=60)

client.loop_forever()
