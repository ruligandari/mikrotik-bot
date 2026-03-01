import socket
import logging
from datetime import datetime
import routeros_api
from src.config import Config

logger = logging.getLogger('mikrotik-bot.infrastructure.mikrotik')

class MikrotikGateway:
    def __init__(self):
        self.host = Config.MIKROTIK_HOST
        self.port = Config.MIKROTIK_PORT
        self.user = Config.MIKROTIK_USER
        self.password = Config.MIKROTIK_PASS
        self.use_ssl = Config.MIKROTIK_USE_SSL

    def _mk_pool(self):
        return routeros_api.RouterOsApiPool(
            self.host,
            username=self.user,
            password=self.password,
            port=self.port,
            plaintext_login=not self.use_ssl,
            use_ssl=self.use_ssl,
            ssl_verify=False,
            ssl_verify_hostname=False,
        )

    def tcp_check(self):
        start = datetime.now()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((self.host, self.port))
            elapsed = (datetime.now() - start).total_seconds() * 1000
            return True, round(elapsed, 1), ''
        except Exception as e:
            return False, None, str(e)
        finally:
            sock.close()

    def get_api_health(self):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            ident = api.get_resource('/system/identity').get()[0]['name']
            res = api.get_resource('/system/resource').get()[0]
            return True, {
                'identity': ident, 
                'version': res.get('version', 'unknown'), 
                'uptime': res.get('uptime', 'unknown')
            }, ''
        except Exception as e:
            return False, None, str(e)
        finally:
            if pool:
                pool.disconnect()

    def fetch_usage(self):
        """Returns list of raw usage dicts from queues."""
        pool = None
        results = []
        try:
            pool = self._mk_pool()
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
                    bi = int(bi_s.strip() or 0)
                    bo = int(bo_s.strip() or 0)
                else:
                    bi = int(q.get('bytes-in', 0))
                    bo = int(q.get('bytes-out', 0))
                
                results.append({
                    'username': uname,
                    'queue_name': name,
                    'bytes_in': bi,
                    'bytes_out': bo,
                    'bytes_total': bi + bo,
                    'max_limit': q.get('max-limit', '0/0')
                })
            return results
        finally:
            if pool:
                pool.disconnect()

    def set_pppoe_profile(self, username, profile):
        """Sets the PPPoE profile for a secret."""
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            resource = api.get_resource('/ppp/secret')
            secrets = resource.get(name=username)
            if not secrets:
                return False, "Secret not found"
            
            resource.set(id=secrets[0]['id'], profile=profile)
            return True, ""
        except Exception as e:
            logger.error(f"MikrotikGateway: Failed to set profile for {username}: {e}")
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def disconnect_pppoe_user(self, username):
        """Disconnects an active PPPoE session."""
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            resource = api.get_resource('/ppp/active')
            actives = resource.get(name=username)
            if not actives:
                return True, "User not active"
            
            for a in actives:
                resource.remove(id=a['id'])
            return True, ""
        except Exception as e:
            logger.error(f"MikrotikGateway: Failed to disconnect {username}: {e}")
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def fetch_active_sessions(self):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            return api.get_resource('/ppp/active').get()
        except:
            return []
        finally:
            if pool:
                pool.disconnect()

    def add_ppp_secret(self, username, password, profile, remote_addr):
        pool = None
        try:
            pool = self._mk_pool()
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
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def remove_ppp_secret(self, username):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            resource = api.get_resource('/ppp/secret')
            secrets = resource.get(name=username)
            if not secrets:
                return False, "Secret not found"
            resource.remove(id=secrets[0]['id'])
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def get_pppoe_secret_status(self, username):
        """Returns (is_disabled, id)"""
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            secrets = api.get_resource('/ppp/secret').get(name=username)
            if not secrets:
                return None, None
            return secrets[0].get('disabled') == 'true', secrets[0].get('id')
        except:
            return None, None
        finally:
            if pool:
                pool.disconnect()

    def enable_pppoe_secret(self, username):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            resource = api.get_resource('/ppp/secret')
            secrets = resource.get(name=username)
            if not secrets:
                return False, "Not found"
            resource.set(id=secrets[0]['id'], disabled='false')
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def disable_pppoe_secret(self, username):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            resource = api.get_resource('/ppp/secret')
            secrets = resource.get(name=username)
            if not secrets:
                return False, "Not found"
            resource.set(id=secrets[0]['id'], disabled='true')
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            if pool:
                pool.disconnect()

    def fetch_ppp_profiles(self):
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            return api.get_resource('/ppp/profile').get()
        except:
            return []
        finally:
            if pool:
                pool.disconnect()

    def get_next_pppoe_ip(self):
        """Calculates next IP based on existing secrets."""
        pool = None
        try:
            pool = self._mk_pool()
            api = pool.get_api()
            secrets = api.get_resource('/ppp/secret').get()
            
            ips = []
            for s in secrets:
                addr = s.get('remote-address')
                if addr and '.' in addr:
                    ips.append(addr)
            
            if not ips:
                return "192.168.10.1"
                
            highest_ip = sorted(ips, key=lambda x: [int(p) for p in x.split('.')])[-1]
            octets = highest_ip.split('.')
            octets[2] = str(int(octets[2]) + 1)
            return ".".join(octets)
        except:
            return "192.168.10.1"
        finally:
            if pool:
                pool.disconnect()
