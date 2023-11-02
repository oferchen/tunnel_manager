import argparse
import logging
import socket
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VXLANManager:
    def __init__(self, bridge_tool='ip'):
        self.default_src_port = 4789
        self.default_dst_port = 4789
        self.bridge_tool = bridge_tool

    def create_vxlan_interface(self, vni, src_host, dst_host, bridge_name, src_port=None, dst_port=None, dev='eth0'):
        src_port = src_port or self.default_src_port
        dst_port = dst_port or self.default_dst_port

        try:
            subprocess.run(['ip', 'link', 'add', f'vxlan{vni}', 'type', 'vxlan',
                            'id', str(vni),
                            'local', src_host,
                            'remote', dst_host,
                            'dev', dev,
                            'dstport', str(src_port)], check=True)
            subprocess.run(['ip', 'link', 'set', f'vxlan{vni}', 'up'], check=True)
            subprocess.run(['ip', 'link', 'set', 'master', bridge_name, f'vxlan{vni}'], check=True)
        except subprocess.CalledProcessError:
            logger.error(f'Error creating VXLAN interface for VNI {vni}')
            sys.exit(1)

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            if self.bridge_tool == 'brctl':
                subprocess.run(['brctl', 'delif', bridge_name, f'vxlan{vni}'], check=True)
            else:  # default to 'ip'
                subprocess.run(['ip', 'link', 'set', f'vxlan{vni}', 'nomaster'], check=True)

            subprocess.run(['ip', 'link', 'del', f'vxlan{vni}'], check=True)
        except subprocess.CalledProcessError:
            logger.error(f'Error deleting VXLAN interface for VNI {vni}')
            sys.exit(1)

    def validate_connectivity(self, src_host, dst_host, vni, port=None, timeout=3):
        port = port or self.default_src_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)

            try:
                # Attempt to establish a TCP connection
                s.connect((dst_host, port))
                logger.info(f'Connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host} is successful.')
            except socket.error as e:
                logger.error(f'Failed to establish connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host}: {e}')

def main():
    parser = argparse.ArgumentParser(description='Create or remove a VXLAN tunnel between two bridges.')
    parser.add_argument('--vni', type=int, required=True, help='VXLAN VNI')
    parser.add_argument('--src-host', required=True, help='Source host IP')
    parser.add_argument('--dst-host', required=True, help='Destination host IP')
    parser.add_argument('--bridge-name', required=True, help='Bridge name to add VXLAN interface')
    parser.add_argument('--src-port', type=int, help='Source VXLAN UDP port')
    parser.add_argument('--dst-port', type=int, help='Destination VXLAN UDP port')
    parser.add_argument('--dev', default='eth0', help='Network device (default: eth0)')
    parser.add_argument('--cleanup', action='store_true', help='Remove VXLAN tunnel instead of creating it')
    parser.add_argument('--validate-connectivity', action='store_true', help='Perform post-deployment connectivity validation')
    parser.add_argument('--bridge-tool', choices=['ip', 'brctl'], default='ip', help='Bridge management tool to use (default: ip)')
    args = parser.parse_args()

    vxlan_manager = VXLANManager(bridge_tool=args.bridge_tool)

    if args.cleanup:
        vxlan_manager.cleanup_vxlan_interface(args.vni, args.bridge_name)
        logger.info(f'VXLAN tunnel {args.vni} removed successfully.')
    else:
        vxlan_manager.create_vxlan_interface(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.dst_port, args.dev)
        logger.info(f'VXLAN tunnel {args.vni} created successfully.')

        if args.validate_connectivity:
            vxlan_manager.validate_connectivity(args.src_host, args.dst_host, args.vni, args.src_port)

if __name__ == '__main__':
    main()
