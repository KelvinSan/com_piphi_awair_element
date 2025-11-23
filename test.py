from xmlrpc.client import ServerProxy
# from zeroconf import ServiceBrowser, Zeroconf
# from time import sleep

# class Listener:
#     def add_service(self, zeroconf, type, name):
#         print(f"Found: {name}")
#     def remove_service(self, zeroconf, type, name):
#         print(f"Removed: {name}")
#     def update_service(self, zeroconf, type, name):
#         pass

# zeroconf = Zeroconf()
# listener = Listener()
# browser = ServiceBrowser(zeroconf, "_http._tcp.local.", listener)  # Replace with your service type, e.g., "_arduino._tcp.local."
# sleep(10)  # Wait for discovery
# zeroconf.close()