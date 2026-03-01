import os
from dotenv import load_dotenv
import routeros_api

load_dotenv('.env')

HOST = os.getenv('MIKROTIK_HOST', '192.168.1.119')
PORT = int(os.getenv('MIKROTIK_PORT', '8728'))
USER = os.getenv('MIKROTIK_USER', '')
PASS = os.getenv('MIKROTIK_PASS', '')

def debug_queues():
    connection = routeros_api.RouterOsApiPool(
        HOST,
        username=USER,
        password=PASS,
        port=PORT,
        plaintext_login=True
    )
    api = connection.get_api()
    queues = api.get_resource('/queue/simple').get()
    
    print(f"Total queues found: {len(queues)}")
    for q in queues:
        print(f"Name: {q.get('name')}, Max-Limit: {q.get('max-limit')}, Bytes: {q.get('bytes')}")
    
    connection.disconnect()

if __name__ == "__main__":
    debug_queues()
