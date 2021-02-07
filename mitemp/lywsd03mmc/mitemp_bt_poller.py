""""
Read data from Mi Temp environmental (Temp and humidity) sensor.
"""

from datetime import datetime, timedelta
import logging
from threading import Lock
from btlewrap.base import BluetoothInterface, BluetoothBackendException



MI_TEMPERATURE = "temperature"
MI_HUMIDITY = "humidity"
MI_BATTERY = "battery"

_LOGGER = logging.getLogger(__name__)


class MiTempBtPoller(object):
    """"
    A class to read data from Mi Temp plant sensors.
    """

    def __init__(self, mac, backend, cache_timeout=600, retries=3, adapter='hci0', ble_timeout=10):
        """
        Initialize a Mi Temp Poller for the given MAC address.
        """

        self._mac = mac
        self._bt_interface = BluetoothInterface(backend, adapter=adapter)
        self._cache = None
        self._cache_timeout = timedelta(seconds=cache_timeout)
        self._last_read = None
        self._fw_last_read = None
        self.retries = retries
        self.ble_timeout = ble_timeout
        self.lock = Lock()   
        self.battery = None
        _LOGGER.debug('INIT++')




    def fill_cache(self):
        """Fill the cache with new data from the sensor."""
        _LOGGER.debug('Filling cache with new sensor data.')

        with self._bt_interface.connect(self._mac) as connection:
            _LOGGER.debug('Send Start.')  
            connection._DATA_MODE_LISTEN=b'\xf4\x01\x00'
            connection.write_handle(0x0038,b'\x01\00')  #enable notifications of Temperature, Humidity and Battery voltage
            _LOGGER.debug('Wait condition1.') 
            connection.wait_for_notification(0x0046, self, self.ble_timeout)
            _LOGGER.debug('Wait condition2.')  
        



    def parameter_value(self, parameter, read_cached=True):
        """Return a value of one of the monitored paramaters.

        This method will try to retrieve the data from cache and only
        request it by bluetooth if no cached value is stored or the cache is
        expired.
        This behaviour can be overwritten by the "read_cached" parameter.
        """
        _LOGGER.debug('parameter_value:'+parameter)
        # Use the lock to make sure the cache isn't updated multiple times
        with self.lock:
            if (read_cached is False) or \
                    (self._last_read is None) or \
                    (datetime.now() - self._cache_timeout > self._last_read):
                _LOGGER.debug('self.fill_cache().')
                self.fill_cache()
            else:
                _LOGGER.debug("Using cache (%s < %s)",
                              datetime.now() - self._last_read,
                              self._cache_timeout)

        if self.cache_available():
            return self._parse_data()[parameter]
        else:
            raise BluetoothBackendException("Could not read data from Mi Temp sensor %s" % self._mac)

    def _check_data(self):
        """Ensure that the data in the cache is valid.

        If it's invalid, the cache is wiped.
        """
        if not self.cache_available():
            return

        parsed = self._parse_data()
        _LOGGER.debug('Received new data from sensor: Temp=%.1f, Humidity=%.1f, Battery = %.1f',
                      parsed[MI_TEMPERATURE], parsed[MI_HUMIDITY], parsed[MI_BATTERY])

        if parsed[MI_HUMIDITY] > 100:  # humidity over 100 procent
            self.clear_cache()
            return

        if parsed[MI_TEMPERATURE] == 0:  # humidity over 100 procent
            self.clear_cache()
            return

    def clear_cache(self):
        """Manually force the cache to be cleared."""
        self._cache = None
        self._last_read = None

    def cache_available(self):
        """Check if there is data in the cache."""
        return self._cache is not None

    def _parse_data(self):
        """Parses the byte array returned by the sensor.

        """
        data = self._cache

        res = dict()
        _LOGGER.debug('_parse_data')
        res[MI_TEMPERATURE] = int.from_bytes(data[0:2],byteorder='little',signed=True)/100
        res[MI_HUMIDITY]  = int.from_bytes(data[2:3],byteorder='little')
        voltage=int.from_bytes(data[3:5],byteorder='little') / 1000.
        res[MI_BATTERY]  =  min(int(round((voltage - 2.1),2) * 100), 100)
        _LOGGER.debug('/_parse_data')
        return res

    @staticmethod
    def _format_bytes(raw_data):
        """Prettyprint a byte array."""
        if raw_data is None:
            return 'None'
        return ' '.join([format(c, "02x") for c in raw_data]).upper()

    def handleNotification(self, handle, raw_data):  # pylint: disable=unused-argument,invalid-name
        """ gets called by the bluepy backend when using wait_for_notification
        """
        _LOGGER.debug('handleNotification')
        if raw_data is None:
            return
        data = raw_data
        self._cache = data
        self._check_data()
        if self.cache_available():
            _LOGGER.debug('self.cache_available()')
            self._last_read = datetime.now()
        else:
            _LOGGER.debug('NO self.cache_available()')
            # If a sensor doesn't work, wait 5 minutes before retrying
            self._last_read = datetime.now() - self._cache_timeout + \
                timedelta(seconds=300)
        
