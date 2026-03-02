from flask import Blueprint, jsonify, request
from sensor_data_processor import sensor_processor

sensor_processor_bp = Blueprint('sensor_processor', __name__)

@sensor_processor_bp.route('/api/process-sensor-data', methods=['POST'])
def process_sensor_data_api():
    """API endpoint to process sensor data"""
    try:
        sensor_processor.process_all_unprocessed_messages()
        return jsonify({
            'success': True,
            'message': 'Sensor data processing completed',
            'processed_count': None  # keep response shape unchanged
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error processing sensor data: {str(e)}'
        }), 500


@sensor_processor_bp.route('/api/sensor-stats')
def get_sensor_stats():
    """Get statistics about unprocessed messages"""
    try:
        unprocessed_messages = sensor_processor.get_unprocessed_mqtt_messages()
        return jsonify({
            'unprocessed_count': len(unprocessed_messages),
            'unprocessed_messages': [
                {
                    'id': msg[0],
                    'timestamp': msg[3].isoformat() if msg[3] else None
                }
                for msg in unprocessed_messages
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting sensor stats: {str(e)}'
        }), 500
