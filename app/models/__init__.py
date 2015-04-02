from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSON
from flask import url_for
import datetime

from app import db
from app.remote import usgs

from .correlation import Correlation  # noqa
from .user import User  # noqa
from .region import Region  # noqa
from .river import River  # noqa
from .section import Section


gages_regions = db.Table('gages_regions',
    db.Column('gage', db.Integer, db.ForeignKey('gages.id')),
    db.Column('region', db.Integer, db.ForeignKey('regions.id'))
)




class Gage(db.Model):
    """
    A Gage is a collection of Sensors at a single location.

    Arguments:
        id (int): Primary key for Gage
        name (string): Nice name for gage
        slug (string): slug used in url
        point (Point): PostGIS Point object. Accepts WKT.
        river_id (int): Foreign key of ``River``.id that the Gage is on.
        river: ``River`` object
        user_id (int): Foreign key of ``User``.id that 'owns' the Gage.
        user: ``User`` object that `owns` the gage.
        visible (boolean): Allows a gage to not be seen on the front end
        zipcode (string): Zip code used to get the weather.
        local_town (string): Local town name, primarily used for getting the weather
        location (string): Descriptive location, often used when Gage is displayed on other pages
        elevation (int): The elevation of the Gage
        elevationUnits (string): Feet or Meters?
        backend_notes (text): Backend info for the Gage for admins.
        started (datetime): When samples started to be collected at this gage
        ended (datetime): If sampling at this gage has stopped, when?
        description (text): Long description for Gage that can contain HTML or Markdown within reason.
        key (string): Secret key that samples are signed with
        short_description (text): Short description for showing on other pages.
        regions: List of ``Region`` objects that this Gage is in.
        sensors: List of ``Sensor`` objects that are part of this Gage.
    """
    __tablename__ = 'gages'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    slug = db.Column(db.String(40), unique=True)
    # primary_sensor_id = db.Column(db.Integer, db.ForeignKey('sensor.id'))
    point = db.Column(Geometry('POINT'))

    river_id = db.Column(db.Integer, db.ForeignKey('rivers.id'))
    river = db.relationship('River', backref='gages')

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref='gages')

    visible = db.Column(db.Boolean)
    zipcode = db.Column(db.String)
    local_town = db.Column(db.String)
    location = db.Column(db.Text)
    elevation = db.Column(db.Integer)
    elevationUnits = db.Column(db.String)
    backend_notes = db.Column(db.Text)
    started = db.Column(db.DateTime)
    ended = db.Column(db.DateTime)
    description = db.Column(db.Text)
    short_description = db.Column(db.Text)
    key = db.Column(db.String)

    regions = db.relationship('Region',
                              secondary=gages_regions,
                              backref=db.backref('gages', lazy='dynamic'))

    def latlon(self):
        """
        Returns a shapely point
        gage.latlon().y for latitude
        gage.latlon().x for longitude
        """
        latlon_point = to_shape(self.point)
        return latlon_point

    def to_json(self):
        """
        Creates a JSON Object from Gage. Used where multiple gages may be
        listed at once.
        """
        json_post = {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'url': url_for('api.get_gage',
                           id=self.id,
                           _external=True)
        }
        return json_post

    def to_long_json(self):
        """
        Cretes a JSON Object from Gage. Used where a single gage is displayed.
        """
        json_post = {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'url': url_for('api.get_gage',
                           id=self.id,
                           _external=True),
            'html': url_for('main.gagepage',
                            slug=self.slug,
                            _external=True),
            'sensors': [sensor.to_gage_json() for sensor in self.sensors],
            'regions': [region.to_json() for region in self.regions]
        }
        return json_post

    def new_sample(self, stype, value, sdatetime):
        """
        Process a new sample for the gage, and finds the right ``Sensor`` that the ``Sample`` should be connected to. \
        If no ``Sensor`` exists for the type of sample, then a new one is created.

        Arguments:
            stype (str): Sensor type
            value (float): Sample value
            sdatetime (datetime): Sample ``datetime`` object
        """
        sensor = Sensor.query.filter_by(gage_id=self.id).filter_by(stype=stype).first()
        if sensor == None:
            sensor = Sensor(gage_id=self.id,
                            stype=stype,
                            local=True)
            db.session.add(sensor)
            db.session.commit()
        sample = Sample(sensor_id=sensor.id, value=value, datetime=sdatetime)
        db.session.add(sample)
        db.session.commit()
        return sample

    def __repr__(self):
        return '<Gage %r>' % self.name

class Sensor(db.Model):
    """
    A single sensor value for a Gage

    Arguments:
        id (int): Primary key for Sensor
        gage_id (int): Foreign ``Gage``.id for the Gage that this Sensor is a part of
        gage: ``Gage`` object for associated Gage
        stype (str): Type of sensor as reported by sending station (gage).
        name (str): Nice display name for sensor
        slug (str): slug for url
        prefix (str): Prefix for value display
        suffix (str): Suffix for value display
        local (boolean): True if the station(gage) sends this sensor's data to the server.
        remote_type (str): Type of remote sensor. Currently only ``'usgs'`` is valid.
        remote_id (int): String element that should be used to query remote sensor.
        remote_parameter (str): Parameter that is required to query remote sensor.
        last (datetime): Last time data was received or retrieved.
        title (str): Title to display on plots.
        xlabel (str): x-axis label to display on plots.
        ylabel (str): y-axis label to display on plots.
        info (JSON): JSON with more detail about sensor for possible future use.
        description (text): Long description of sensor that can contain HTML or Markdown within reason.
        backend_notes (text): Backend info for admins.
        minimum (float): Lowest measurement of sensor. Used for plot formatting.
        maximum (float): Highest measurement of sensor. Used for plot formatting.
        started (datetime): Datetime that sample collection started.
        ended (datetime): Datetime that sample collection ended.
        samples: List of ``Sample`` objects from Sensor.
    """
    __tablename__ = 'sensors'

    id = db.Column(db.Integer, primary_key=True)

    gage_id = db.Column(db.Integer, db.ForeignKey('gages.id'))
    gage = db.relationship('Gage',
                           backref=db.backref('sensors', lazy='dynamic'))

    stype = db.Column(db.String(80))
    name = db.Column(db.String(80))
    slug = db.Column(db.String(40))
    prefix = db.Column(db.String(10))
    suffix = db.Column(db.String(10))
    local = db.Column(db.Boolean)
    remote_type = db.Column(db.String)
    remote_id = db.Column(db.String)
    remote_parameter = db.Column(db.String)
    last = db.Column(db.DateTime)
    title = db.Column(db.String)
    xlabel = db.Column(db.String)
    ylabel = db.Column(db.String)
    info = db.Column(JSON)
    description = db.Column(db.Text)
    backend_notes = db.Column(db.Text)
    minimum = db.Column(db.Float)
    maximum = db.Column(db.Float)
    started = db.Column(db.DateTime)
    ended = db.Column(db.DateTime)

    def timediff(self, dateTime):
        delta = datetime.datetime.now()-datetime.timedelta(minutes=60)
        return self.stype, str(dateTime), str(datetime.datetime.now()), str(dateTime > delta), str(datetime.datetime.now() - dateTime)

    def recent(self):
        """
        Return recent sample value.
        """
        delta = datetime.datetime.now()-datetime.timedelta(minutes=60)
        print delta
        sample = Sample.query.filter_by(sensor_id=self.id).order_by(Sample.datetime.desc()).first()
        if sample is not None and (self.local is True or sample.datetime > delta):
            print self.timediff(sample.datetime), 'A'
            return sample
        elif sample is not None and self.local is False and sample.datetime < delta:
            print self.timediff(sample.datetime), 'B'
            if self.remote_parameter is None:
                print self.timediff(sample.datetime), 'C'
                usgs.get_samples(self, self.remote_id, startDT=sample.datetime, endDT=datetime.datetime.utcnow())
            else:
                print self.timediff(sample.datetime), 'D'
                usgs.get_samples(self, self.remote_id, startDT=sample.datetime, endDT=datetime.datetime.utcnow(), parameter=self.remote_parameter)
            print self.timediff(sample.datetime), 'E'
            return Sample.query.filter_by(sensor_id=self.id).order_by(Sample.datetime.desc()).first()
        elif sample is None and self.local is False:
            print self.timediff(sample.datetime), 'F'
            if self.remote_parameter is None:
                print self.timediff(sample.datetime), 'G'
                usgs.get_samples(self, self.remote_id, period='P7D')
            else:
                print self.timediff(sample.datetime), 'H'
                usgs.get_samples(self, self.remote_id, period='P7D', parameter=self.remote_parameter)
            print self.timediff(sample.datetime), 'I'
            return Sample.query.filter_by(sensor_id=self.id).order_by(Sample.datetime.desc()).first()
        else:
            print self.timediff(sample.datetime), 'J'
            pass



    def to_json(self):
        """
        Creates a JSON object from sensor. Used where multiple sensors may be displayed at once.
        """
        json_post = {
            'id': self.id,
            'type': self.stype,
            'url': url_for('api.get_sensor', id=self.id, _external=True)
        }
        return json_post

    def to_long_json(self):
        """
        Creates a JSON object from sensor. Used where a single sensor will be displayed.
        """
        sample = Sample.query.filter_by(sensor_id=self.id).order_by(Sample.datetime.desc()).first()
        json_post = {
            'id': self.id,
            'type': self.stype,
            'description': self.description,
            'minimum': self.minimum,
            'maximum': self.maximum,
            'started': self.started,
            'ended': self.ended,
            'url': url_for('api.get_sensor', id=self.id, _external=True),
            'gage': self.gage.to_json(),
            'recent_sample': sample.to_sensor_json()
        }
        return json_post

    def to_gage_json(self):
        """
        Creates a JSON object from sensor. Displayed with gage JSON and includes
        most recent sample.
        """
        sample = Sample.query.filter_by(sensor_id=self.id).order_by(Sample.datetime.desc()).first()
        json_post = {
            'id': self.id,
            'type': self.stype,
            'url': url_for('api.get_sensor', id=self.id, _external=True),
            'recent_sample': sample.to_sensor_json()
        }
        return json_post

    def to_sample_json(self):
        """
        Creates a JSON object from sensor. Displayed with sample JSON and includes gage information.
        """
        json_sensor = {
            'id': self.id,
            'type': self.stype,
            'gage': self.gage.to_json(),
            'url': url_for('api.get_sensor', id=self.id, _external=True)
        }
        return json_sensor

    def __repr__(self):
        return '<Sensor %r>' % self.id


class Sample(db.Model):
    """
    Sample model

    Arguments:
        id (int): Primary Sample key
        sensor_id (int): Foreign ``Sensor``.id key
        sensor: ``Sensor`` object related to this sample
        datetime (datetime): ``datetime`` object of this sample
        value (float): Value of sample
    """
    __tablename__ = 'samples'

    id = db.Column(db.Integer, primary_key=True)

    sensor_id = db.Column(db.Integer, db.ForeignKey('sensors.id'))
    sensor = db.relationship('Sensor', backref=db.backref('samples'))

    datetime = db.Column(db.DateTime)
    value = db.Column(db.Float)

    def to_json(self):
        """
        Creates a JSON object from Sample. Used where multiple samples will be displayed at once.
        """
        json_sample = {
            'id': self.id,
            'sensor': self.sensor.to_sample_json(),
            'value': self.value,
            'datetime': self.datetime,
            'url': url_for('api.get_sample', id=self.id, _external=True)
        }
        return json_sample

    def to_sensor_json(self):
        """
        Creates a JSON object from Sample for used with Sensor JSON.
        """
        json_sample = {
            'id': self.id,
            'value': self.value,
            'datetime': str(self.datetime),
            'url': url_for('api.get_sample', id=self.id, _external=True)
        }
        return json_sample

    def __repr__(self):
        return '<Sample %r>' % self.id
