import aiohttp
from getmac import get_mac_address
from lib.core.data_manager import coordinate_data_storage
from lib.sensors.helpers import SensorEntity
from lib.sensors.integrations.native.awair_element.exceptions import ConnectionFailedException, ConnectionTimeoutException, UnknownException
from lib.core.const import PiPhiNetwork
from config.SysLogger import sys_log
import http
import httpx
from .validator import UISchema
from . import context
DOMAIN = "awair_element"

class Integration(SensorEntity):
    
    def __init__(self) -> None:
        self.config = {
            "polling": True,
            "interval": 60
        }
        self.awair_collection:dict[str,float | None] = {}
        self.temp = None
        self.humidity = None
        self.dew_pt = None
        self.co2 = None
        self.co2_est = None
        self.co2_est_baseline = None
        self.voc = None
        self.voc_baseline = None
        self.voc_h2_raw = None
        self.voc_ethanol_raw = None
        self.pm2_5 = None
        self.pm10 = None
        self.co2_est_baseline = None
        self.aqi = None
        self.collection_duration = 300
        self.session = None
        self.settings_url = None
        self.awair_settings = None
        
        
    async def add_entity(self,uipayload:UISchema,piphi:PiPhiNetwork):
        config = {
            "domain":"awair_element",
            "config":{
                "ip_address":uipayload.ip_address,
                "mac_address":get_mac_address(ip=uipayload.ip_address),
                "type":"sensor"
            },
            "type":"sensor"
        }
        entry = await piphi.add_piphi_network_entity(device=config)
        return entry
        
    async def connect(self, uipayload:UISchema):
        backup_settings_url = f"http://{uipayload.ip_address}/settings/config/data"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(backup_settings_url) as res:
                    if res.status != http.HTTPStatus.OK:
                        raise Exception(f"FAILURE: Connection to Awair Element has failed for address {uipayload.ip_address}")
                    else:
                        sys_log.info("SUCCESS: Awair Element connection successful")
        except Exception as e:
            raise e
        
    async def get_sensor_data(self):
        return self.awair_collection
        
    async def update(self):
        async with httpx.AsyncClient() as client:
            try:
                ip = context.get("integration_config")["config"]['ip_address']
                response:httpx.Response = await client.get(f"http://{ip}/air-data/latest",timeout=60.0)
                if response.status_code == 200:
                    data = response.json()
                    self.temp = data['temp']
                    self.humidity = data['humid']
                    self.dew_pt = data['dew_point']
                    self.aqi = data['score']
                    self.co2 = data['co2']
                    self.co2_est = data['co2_est']
                    self.voc = data['voc']
                    self.voc_baseline = data['voc_baseline']
                    self.voc_h2_raw = data['voc_h2_raw']
                    self.co2_est_baseline = data['co2_est_baseline']
                    self.voc_ethanol_raw = data['voc_ethanol_raw']
                    self.pm2_5 = data['pm25']
                    self.pm10 = data['pm10_est']
                    self.awair_collection['temp'] = self.temp
                    self.awair_collection['humidity'] = self.humidity
                    self.awair_collection['dew_pt'] = self.dew_pt
                    self.awair_collection['aqi'] = self.aqi
                    self.awair_collection['co2'] = self.co2
                    self.awair_collection['co2_est'] = self.co2_est
                    self.awair_collection['voc'] = self.voc
                    self.awair_collection['voc_baseline'] = self.voc_baseline
                    self.awair_collection['voc_h2_raw'] = self.voc_h2_raw
                    self.awair_collection['co2_est_baseline'] = self.co2_est_baseline
                    self.awair_collection['voc_ethanol_raw'] = self.voc_ethanol_raw
                    self.awair_collection['pm2_5'] = self.pm2_5
                    self.awair_collection['pm10'] = self.pm10
                    await coordinate_data_storage(data=self.awair_collection,domain=context.get("integration_config")['domain'], integration_id=context.get("integration_config")['uuid'])
            except httpx.ConnectError as connection_reset:
                sys_log.error(connection_reset)
                raise ConnectionFailedException("Connection to awair has failed")
            except httpx.ConnectTimeout as timeout:
                sys_log.error("Connection to Awair has timed out shutting down data collection")
                raise ConnectionTimeoutException("Connection to Awair has timed out shutting down data collection")
            except Exception as e:
                raise UnknownException(f"Unknown Exception for Awair {str(e)}")
