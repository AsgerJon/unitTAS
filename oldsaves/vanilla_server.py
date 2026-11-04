"""Mojang's 1.7.10 server, run headless for one world: its folder, settings, operator, console and stop."""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

# 1.7.10's server wants Java 8: UNITTAS_JAVA8 names one, else the usual Linux place for it, else the first java found
JAVA = (os.environ.get('UNITTAS_JAVA8')
        or ('/usr/lib/jvm/java-8-openjdk/bin/java' if os.path.isfile('/usr/lib/jvm/java-8-openjdk/bin/java') else None)
        or shutil.which('java'))


def offline_uuid(name):
    """As 1.7.10's offline mode: UUID.nameUUIDFromBytes("OfflinePlayer:" + name)."""
    h = bytearray(hashlib.md5(('OfflinePlayer:' + name).encode('utf-8')).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(h))


class Server:
    def __init__(self, folder, jar, port, seed, level_type='DEFAULT', generator='', operator='Builder', log=print):
        self.folder, self.jar, self.port, self.log = folder, jar, port, log
        self.process = None
        self.lines = []
        self.ready = threading.Event()
        os.makedirs(folder, exist_ok=True)
        properties = {
            'level-name': 'world', 'level-seed': str(seed), 'level-type': level_type, 'generator-settings': generator,
            'server-port': str(port), 'server-ip': '127.0.0.1', 'online-mode': 'false', 'gamemode': '0',
            'difficulty': '2', 'allow-nether': 'true', 'allow-flight': 'true', 'enable-command-block': 'true',
            'spawn-protection': '0', 'generate-structures': 'true', 'spawn-monsters': 'true', 'spawn-animals': 'true',
            'spawn-npcs': 'true', 'pvp': 'true', 'max-players': '4', 'view-distance': '10', 'white-list': 'false',
            'motd': 'unitTAS vanilla world builder', 'enable-query': 'false', 'enable-rcon': 'false',
            'snooper-enabled': 'false', 'op-permission-level': '4',
        }
        with open(os.path.join(folder, 'server.properties'), 'w') as f:
            for key, value in properties.items():
                f.write('%s=%s\n' % (key, value))
        # the Minecraft EULA is the user's to accept: their own run/oldsaves/server/eula.txt, copied, never written here
        accepted = os.path.join(os.path.dirname(os.path.abspath(jar)), 'eula.txt')
        if not os.path.isfile(accepted) or 'eula=true' not in open(accepted).read():
            raise RuntimeError('The vanilla server needs the Minecraft EULA (https://aka.ms/MinecraftEULA) accepted: '
                               'put a line "eula=true" in %s yourself if you accept it.' % accepted)
        with open(accepted) as src, open(os.path.join(folder, 'eula.txt'), 'w') as dst:
            dst.write(src.read())
        with open(os.path.join(folder, 'ops.json'), 'w') as f:
            json.dump([{'uuid': str(offline_uuid(operator)), 'name': operator, 'level': 4}], f)

    def start(self, timeout=300):
        self.process = subprocess.Popen([JAVA, '-Xmx2G', '-Xms1G', '-jar', os.path.abspath(self.jar), 'nogui'],
                                        cwd=self.folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()
        if not self.ready.wait(timeout):
            raise TimeoutError('the server did not start in %d s; its last lines: %s' % (timeout, self.lines[-10:]))

    def _pump(self):
        with open(os.path.join(self.folder, 'console.log'), 'a') as log:
            for line in self.process.stdout:
                line = line.rstrip('\n')
                self.lines.append(line)
                log.write(line + '\n')
                log.flush()
                if 'Done (' in line and 'For help, type "help"' in line:
                    self.ready.set()

    def console(self, line):
        self.process.stdin.write(line + '\n')
        self.process.stdin.flush()

    def wait_line(self, text, since, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for line in self.lines[since:]:
                if text in line:
                    return line
            time.sleep(0.2)
        raise TimeoutError('no "%s" from the server in %d s' % (text, timeout))

    def save_and_stop(self, timeout=300):
        mark = len(self.lines)
        self.console('save-all')
        self.wait_line('Saved the world', mark, timeout)
        self.console('stop')
        self.process.wait(timeout)
