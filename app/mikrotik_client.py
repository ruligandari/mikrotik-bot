import os
import socket
import logging
from datetime import datetime
import routeros_api

logger = logging.getLogger('mikrotik-bot.mikrotik')

HOST = os.getenv('MIKROTIK_HOST', '192.168.1.119')
PORT = int(os.getenv('MIKROTIK_PORT', '8728'))
USER = os.getenv('MIKROTIK_USER', '')
PASS = os.getenv('MIKROTIK_PASS', '')
USE_SSL = os.getenv('MIKROTIK_USE_SSL', 'false').lower() == 'true'

def _mk_pool():
    return routeros_api.RouterOsApiPool(
        HOST,
        username=USER,
        password=PASS,
        port=PORT,
        plaintext_login=not USE_SSL,
        use_ssl=USE_SSL,
        ssl_verify=False,
        ssl_verify_hostname=False,
    )

def tcp_check():
    start = datetime.now()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    try:
        sock.connect((HOST, PORT))
        elapsed = (datetime.now() - start).total_seconds() * 1000
        return True, round(elapsed, 1), ''
    except Exception as e:
        return False, None, str(e)
    finally:
        sock.close()

def get_api_health():
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        ident = api.get_resource('/system/identity').get()[0]['name']
        res = api.get_resource('/system/resource').get()[0]
        return True, {'identity': ident, 'version': res.get('version', 'unknown'), 'uptime': res.get('uptime', 'unknown')}, ''
    except Exception as e:
        return False, None, str(e)
    finally:
        if pool:
            pool.disconnect()

def _parse_bytes(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        return int(val.strip() or 0)
    return 0

def fetch_usage():
    pool = None
    results = []
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/queue/simple')
        queues = resource.call('print', {'stats': ''})
        for q in queues:
            name = q.get('name', '')
            if not (name.startswith('<pppoe-') and name.endswith('>')):
                continue
            uname = name[len('<pppoe-'):-1]
            bytes_raw = q.get('bytes', '0/0')
            if isinstance(bytes_raw, str) and '/' in bytes_raw:
                bi_s, bo_s = bytes_raw.split('/', 1)
                bi = _parse_bytes(bi_s)
                bo = _parse_bytes(bo_s)
            else:
                bi = _parse_bytes(q.get('bytes-in', 0))
                bo = _parse_bytes(q.get('bytes-out', 0))
            bt = bi + bo
            # Also get current max-limit to check status if needed
            max_limit = q.get('max-limit', '0/0')
            results.append({
                'username': uname,
                'queue_name': name,
                'bytes_in': bi,
                'bytes_out': bo,
                'bytes_total': bt,
                'max_limit': max_limit
            })
        return results
    finally:
        if pool:
            pool.disconnect()

def set_queue_rate(queue_name, rate):
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/queue/simple')
        q_id = resource.get(name=queue_name)[0]['id']
        resource.set(id=q_id, **{'max-limit': rate})
        logger.info(f"Rate for {queue_name} set to {rate}")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to set rate for {queue_name}: {e}")
        return False, str(e)
    finally:
        if pool:
            pool.disconnect()

def disconnect_pppoe_user(pppoe_name):
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/active')
        actives = resource.get(name=pppoe_name)
        if not actives:
            logger.info(f"User {pppoe_name} not active, no need to disconnect")
            return True, "User not active"
        
        for a in actives:
            resource.remove(id=a['id'])
            logger.info(f"Disconnected active session for {pppoe_name} (id: {a['id']})")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to disconnect user {pppoe_name}: {e}")
        return False, str(e)
    finally:
        if pool:
            pool.disconnect()

def set_pppoe_profile(username, profile):
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/secret')
        secrets = resource.get(name=username)
        if not secrets:
            logger.error(f"PPP Secret for {username} not found")
            return False, "Secret not found"
        
        resource.set(id=secrets[0]['id'], profile=profile)
        logger.info(f"PPP Profile for {username} set to {profile}")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to set PPP profile for {username}: {e}")
        return False, str(e)
    finally:
        if pool:
            pool.disconnect()

def fetch_active_sessions():
    """Returns list of active PPP sessions."""
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/active')
        return resource.get()
    except:
        return []
    finally:
        if pool:
            pool.disconnect()

def get_next_pppoe_ip():
    """Finds highest IP in Secrets and increments 3rd octet. Fallback: 192.168.10.1"""
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/secret')
        secrets = resource.get()
        
        ips = []
        for s in secrets:
            addr = s.get('remote-address')
            if addr and '.' in addr:
                ips.append(addr)
        
        if not ips:
            return "192.168.10.1"
            
        # Parse for actually highest 3rd octet
        highest_ip = sorted(ips, key=lambda x: [int(p) for p in x.split('.')])[-1]
        octets = highest_ip.split('.')
        # Increment 3rd octet, keep others same. 
        octets[2] = str(int(octets[2]) + 1)
        return ".".join(octets)
    except Exception as e:
        logger.error(f"IP Calc error: {e}")
        return "192.168.10.1"
    finally:
        if pool:
            pool.disconnect()

def add_ppp_secret(username, password, profile, remote_addr):
    """Creates a new PPPoE Secret."""
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/secret')
        resource.add(
            name=username,
            password=password,
            profile=profile,
            service='pppoe',
            **{'remote-address': remote_addr}
        )
        return True, ""
    except Exception as e:
        logger.error(f"Failed to add secret {username}: {e}")
        return False, str(e)
    finally:
        if pool:
            pool.disconnect()

def remove_ppp_secret(username):
    """Deletes a secret from MikroTik."""
    pool = None
    try:
        pool = _mk_pool()
        api = pool.get_api()
        resource = api.get_resource('/ppp/secret')
        secrets = resource.get(name=username)
        if not secrets:
            return False, "Secret not found"
        resource.remove(id=secrets[0]['id'])
        return True, ""
    except Exception as e:
        logger.error(f"Failed to remove secret {username}: {e}")
        return False, str(e)
    finally:
        if pool:
            pool.disconnect()
