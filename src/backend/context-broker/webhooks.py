from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import json
from datetime import datetime, timedelta
import pytz
from paho.mqtt.client import Client
import os
import logging
import logging.config
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logging.config.fileConfig('../../logging.conf')
logger = logging.getLogger("WEBHOOK")

token = os.getenv('GRAFANA_READ_AND_WRITE')
org = 'students'
bucket = 'APARS'
client = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

MQTT_BROKER = os.getenv("MQTT_ADDRESS")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_TOPICS = {
    "station": "station",
    "car": "car",
    "satellite": "satellite"
}


def toUTC(timestamp):
    if timestamp.endswith("Z"):
        utc_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        adjusted_time = utc_time - timedelta(hours=2)
        return adjusted_time.isoformat(timespec='microseconds')
    else:
        local_time = datetime.fromisoformat(timestamp)
        utc_plus_2 = pytz.timezone('Europe/Athens')
        localized_time = utc_plus_2.localize(local_time)
        utc_time = localized_time.astimezone(pytz.utc)
        return utc_time.replace(tzinfo=None).isoformat(timespec='microseconds')

def send_to_influxdb(data, measurement_type):
    try:
        payload = data["data"][0]

        point = Point(measurement_type) \
                .tag("id", str(payload['id'])) \
                .field("pm1", float(payload['pm1']['value'])) \
                .field("pm25", float(payload['pm25']['value'])) \
                .field("pm10", float(payload['pm10']['value'])) \
                .field("co", float(payload['co']['value'])) \
                .field("co2", float(payload['co2']['value'])) \
                .time(toUTC(payload['dateObserved']['value'])) \
                .field("latitude", float(payload['location']['value']['coordinates'][0])) \
                .field("longitude", float(payload['location']['value']['coordinates'][1]))
        

        write_api.write(bucket=bucket, org=org, record=point)
        
        logger.info(f"Data for ID '{payload['id']}' successfully written to InfluxDB under measurement '{measurement_type}'.")
        
    except Exception as e:
        logger.error(f"Failed to write data to InfluxDB: {str(e)}")


def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker with result code {rc}")
    # Subscribe to topics
    for topic in MQTT_TOPICS.values():
        client.subscribe(topic)
        logger.info(f"Subscribed to topic: {topic}")


def on_message(client, userdata, msg):
    logger.info(f"Received MQTT message on topic {msg.topic}: {msg.payload.decode()}")
    try:
        data = json.loads(msg.payload.decode())
        if msg.topic == MQTT_TOPICS["car"]:
            send_to_influxdb(data, 'car_metrics')
        elif msg.topic == MQTT_TOPICS["satellite"]:
            send_to_influxdb(data, 'satellite_metrics')
        elif msg.topic == MQTT_TOPICS["station"]:
            send_to_influxdb(data, 'station_metrics')
    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}")
        

def start_mqtt():
    mqtt_client = Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_forever() 


if __name__ == '__main__':
    start_mqtt()
