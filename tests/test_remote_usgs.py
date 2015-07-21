import vcr

from .test_basics import BasicTestCase

from app.models import Sensor
from app.remote import usgs

my_vcr = vcr.VCR(
    match_on = ['method']
)


class TestUSGS(BasicTestCase):
    SITE_NUM = 235127

    @my_vcr.use_cassette('tests/fixtures/usgs_get_multiple_level')
    def test_get_multiple_level(self):
        usgs_level_sensors = Sensor.query.filter_by(local=False,
                                                    remote_type='usgs',
                                                    remote_parameter=None)\
                                         .with_entities(Sensor.id).all()
        usgs.get_multiple_level([sensor[0] for sensor in usgs_level_sensors])

    @my_vcr.use_cassette('tests/fixtures/usgs_get_other_samples')
    def test_get_other_sample(self):
        usgs_other_sensors = Sensor.query.filter(Sensor.local == False,
                                                 Sensor.remote_type == 'usgs',
                                                 Sensor.remote_parameter != None)\
                                         .with_entities(Sensor.id).all()
        for sensor in usgs_other_sensors:
            usgs.get_other_sample(sensor[0])