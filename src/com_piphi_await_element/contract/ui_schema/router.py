
from fastapi import APIRouter


router = APIRouter(tags=['ui_schema'])

@router.get('/ui')
async def get_ui_schema():
    schema = {
        "title": "Awair Element API Configuration",
        "description":
            "Configuration for Awair Element Local  integration.",
        "type": "object",
        "required": ["device_ip"],
        "properties": {
            "device_ip": {
                "type": "string",
                "title": "Device IP Address",
                "description":
                    "IPv4 address of the Awair Element on your LAN (e.g., 192.168.1.100). Endpoint: http://{device_ip}/air-data/latest",
                "pattern":
                    "^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$",
                "examples": ["192.168.1.100"],
                "errorMessage": "Please provide a valid IPv4 address",
            },
            "device_mac": {
                "type": "string",
                "title": "Device MAC Address (Optional)",
                "description":
                    "MAC for whitelisting or discovery (12-digit hex starting with '70', e.g., 70:88:6B:00:00:00). Found on device back.",
                "pattern":
                    "^70:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}$",
                "examples": ["70:88:6B:00:00:00"],
                "errorMessage": "Please enter a valid mac address",
            },
        },
    }
    
    return dict(schema=schema)