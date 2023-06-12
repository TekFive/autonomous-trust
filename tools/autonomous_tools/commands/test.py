import os
import random
import subprocess
import time

from ..config import packages, sources
from ..docker.build import build_containers
from ..docker.network import create_network, get_default_route_info
from ..docker.run import run_container, run_interactive_container


def test(num_nodes: int = 4, debug: bool = False, tunnel: bool = False, force: bool = False, quick=False):
    debug_build = debug == 'all' or debug == 'build'
    debug_run = debug == 'all' or debug == 'run'
    if not quick:
        build_containers(which='devel', debug=debug_build, force=force)
        build_containers(which='test', debug=debug_build, force=force)

    create_network(force=force)  # host not needed for these tests
    gateway = get_default_route_info()[0]

    mount_targets = ['tests', 'coverage', 'tox.ini']

    min_sec = 1
    max_sec = 5
    extras = ['-e', 'ROUTER=%s' % gateway, '-e', 'AUTONOMOUS_TRUST_ARGS="--live --test"']
    for pkg, path in packages.items():
        suffix = ''
        if 'inspector' in pkg:
            suffix = 'i'

        mounts = []
        for mnt in mount_targets:
            mounts += [(os.path.join(path, mnt), os.path.join('/app', mnt))]
        for base, src in sources[pkg]:
            mounts += [(os.path.join(base, src), os.path.join('/app', src))]

        containers = ''
        for n in range(1, num_nodes + 1):
            ident = 'at-%d' % n
            containers += ' ' + ident
            run_container(ident, 'autonomous-trust', 'at-net', net_admin=True, extra_args=extras)
            time.sleep(random.randint(min_sec, max_sec))
        time.sleep(1)
        ip_file = os.path.join(path, 'docker_ips')
        with open(ip_file, 'a') as ip_list:
            for n in range(1, num_nodes + 1):
                ident = 'at-%d' % n
                fmt = '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
                ip = subprocess.getoutput("docker inspect --format '%s' %s" % (fmt, ident))
                ip_list.write(ip + '\n')
        run_interactive_container('at-test', 'autonomous-trust-test', 'at-net', mounts=mounts,
                                  extra_args=extras, net_admin=True, debug_run=debug_run, tunnel=tunnel, blocking=True)
        # tests complete
        for n in range(1, num_nodes + 1):  # FIXME auto-logging instead for failing containers
            ident = 'at-%d' % n
            with open(ident + suffix + '.log', 'w') as lg:
                lg.write(subprocess.getoutput('docker logs %s' % ident))
        subprocess.call(('docker stop' + containers).split())
        os.remove(ip_file)
        time.sleep(2)
