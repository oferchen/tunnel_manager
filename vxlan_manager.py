import argparse
import subprocess
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VXLANManager:
    def __init__(self):
        self.default_src_port = 4789
        self.default_dst_port = 4789

    def create_vxlan_interface(self, vni, src_host, dst_host, bridge_name, src_port=None, dst_port=None):
        src_port = src_port or self.default_src_port
        dst_port = dst_port or self.default_dst_port

        try:
            subprocess.call(['ip', 'link', 'add', f'vxlan{vni}', 'type', 'vxlan',
                            'id', str(vni),
                            'local', src_host,
                            'remote', dst_host,
                            'dev', 'eth0',
                            'dstport', str(src_port)])
            subprocess.call(['ip', 'link', 'set', f'vxlan{vni}', 'up'])
            subprocess.call(['brctl', 'addif', bridge_name, f'vxlan{vni}'])
        except subprocess.CalledProcessError as e:
            logger.error('Error creating VXLAN interface: {}'.format(e))
            sys.exit(1)

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            subprocess.call(['brctl', 'delif', bridge_name, f'vxlan{vni}'])
            subprocess.call(['ip', 'link', 'del', f'vxlan{vni}'])
        except subprocess.CalledProcessError as e:
            logger.error('Error deleting VXLAN interface: {}'.format(e))
            sys.exit(1)

def create_vxlan_tunnel(vni, src_host, dst_host, bridge_name, src_port, dst_port):
    vxlan_manager = VXLANManager()
    vxlan_manager.create_vxlan_interface(vni, src_host, dst_host, bridge_name, src_port, dst_port)

def cleanup_vxlan_tunnel(vni, bridge_name):
    vxlan_manager = VXLANManager()
    vxlan_manager.cleanup_vxlan_interface(vni, bridge_name)

def main():
    parser = argparse.ArgumentParser(description='Create or remove a VXLAN tunnel between two bridges.')
    parser.add_argument('--vni', type=int, required=True, help='VXLAN VNI')
    parser.add_argument('--src-host', required=True, help='Source host IP')
    parser.add_argument('--dst-host', required=True, help='Destination host IP')
    parser.add_argument('--bridge-name', required=True, help='Bridge name to add VXLAN interface')
    parser.add_argument('--src-port', type=int, help='Source VXLAN UDP port')
    parser.add_argument('--dst-port', type=int, help='Destination VXLAN UDP port')
    parser.add_argument('--cleanup', action='store_true', help='Remove VXLAN tunnel instead of creating it')
    parser.add_argument('--validate-connectivity', action='store_true', help='Perform post-deployment connectivity validation')

    args = parser.parse_args()

    if args.cleanup:
        cleanup_vxlan_tunnel(args.vni, args.bridge_name)
        logger.info('VXLAN tunnel {} removed successfully.'.format(args.vni))
    else:
        create_vxlan_tunnel(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.dst_port)
        logger.info('VXLAN tunnel {} created successfully.'.format(args.vni))
        
        if args.validate_connectivity:
            validate_connectivity(args.src_host, args.dst_host, args.vni)

if __name__ == '__main__':
    main()
