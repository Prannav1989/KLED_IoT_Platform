import paho.mqtt.client as mqtt

BROKER = "au1.cloud.thethings.network"        # example: "eu1.cloud.thethings.network"
PORT = 8883
USERNAME = "mumbai@ttn"                # your TTN application-id@ttn
PASSWORD = "NNSXS.WP7KWYETRKS4HG2Q64PN7DDMIQP76BAUVMFAPAQ.ADKPPPCQA47UYDAHKCZLWG437YBDC2KOKQNR7J6LR7YTS4J3FU4A"          # your API key with MQTT read permission
TOPIC = "v3/mumbai@ttn/devices/+/up"   # change to your app

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)
    if rc == 0:
        print("SUBSCRIBING:", TOPIC)
        client.subscribe(TOPIC)
    else:
        print("Connection failed")

def on_message(client, userdata, msg):
    print("\n📡 MESSAGE RECEIVED")
    print("Topic :", msg.topic)
    print("Payload :", msg.payload.decode())

def on_disconnect(client, userdata, rc):
    print("Disconnected with result code:", rc)

client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)

# TTN requires TLS
client.tls_set()
client.tls_insecure_set(True)

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

print("Connecting to", BROKER, "...")
client.connect(BROKER, PORT, 60)

client.loop_forever()
