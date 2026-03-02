from datetime import datetime
from extensions import db
from models import Parameter, SensorModelParameter


def attach_model_parameters_to_device(device_id, sensor_model_id, user_id):
    """
    Copy sensor_model_parameters → parameters table
    """
    model_params = SensorModelParameter.query.filter_by(
        sensor_model_id=sensor_model_id
    ).all()

    if not model_params:
        raise Exception("No parameters found for selected sensor model")

    created_count = 0

    for mp in model_params:
        # Avoid duplicates
        exists = Parameter.query.filter_by(
            device_id=device_id,
            name=mp.parameter_name
        ).first()

        if exists:
            continue

        param = Parameter(
            name=mp.parameter_name,
            sensor_type=mp.parameter_type,
            unit=mp.unit,
            device_id=device_id,
            parameter_mode='live',
            is_result='Y',
            user_id=user_id,
            created_at=datetime.utcnow()
        )

        db.session.add(param)
        created_count += 1

    db.session.commit()
    return created_count
