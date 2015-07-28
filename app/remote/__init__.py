import datetime
import logging

from app.database import db
from app.models import Sample

logger = logging.getLogger(__name__)


def add_new_sample(sensor_id, dt, svalue, deltaminutes=10):
    """
    Adds a new sample with an associacted remote sensor
    if there hasn't been a sample recorded within the last deltaminutes
    (default is 10).
    Arguments:
        sensor_id (int): Primary key for sensor
        dt (datetime): Datetime of sample
        svalue (float): Value of sample
    """
    delta = datetime.datetime.now() - datetime.timedelta(minutes=deltaminutes)
    sample = Sample.query.filter_by(sensor_id=sensor_id)\
                         .order_by(Sample.datetime.desc()).first()
    if sample is None or (sample.datetime > delta and
                          (sample.datetime != dt.replace(tzinfo=None))):
        new_sample = Sample(sensor_id=sensor_id,
                            value=svalue,
                            datetime=dt)
        db.session.add(new_sample)
        db.session.commit()
        logger.info('Saved sample ({0} - {1} - {2}) for sensor {3}'
                                .format(new_sample.id,
                                        svalue,
                                        dt,
                                        sensor_id))
    else:
        message = ('Discarded sample ({0} - {1}) for sensor {2}, compared to ({3} - {4})'
                   .format(svalue, dt,
                           sensor_id,
                           sample.value,
                           sample.datetime))
        if sample.datetime == dt.replace(tzinfo=None):
            message = message + ' Sample times are the same.'
        if sample.datetime < delta:
            message = message + ' Last sample was more than {0} min ago'.format(deltaminutes)
        else:
            message = message + ' Last sample was less than {0} min ago'.format(deltaminutes)
        logger.warning(message)
