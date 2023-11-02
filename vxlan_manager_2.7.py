# File: vxlan_manager.py

import argparse
import csv
import io
import json
import logging
import re
import socket
import subprocess
import sys
from xml.etree import ElementTree

# Configure logging with timestamps
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VXLANManagerError(Exception):
    """Custom exception for VXLAN Manager errors."""
    pass

class VXLANManager:
    def __init__(self, bridge_tool='ip'):
        self.default_src_port = 4789
        self.default_dst_port = 4789
        self.bridge_tool = bridge_tool

    def create_vxlan_interface(self, vni, src_host, dst_host, bridge_name, src_port=None, dst_port=None, dev='eth0'):
        src_port = src_port or self.default_src_port
        dst_port = dst_port or self.default_dst_port

        try:
            subprocess.check_output(['ip', 'link', 'add', 'vxlan{}'.format(vni), 'type', 'vxlan',
                                     'id', str(vni),
                                     'local', src_host,
                                     'remote', dst_host,
                                     'dev', dev,
                                     'dstport', str(dst_port)])
            subprocess.check_output(['ip', 'link', 'set', 'vxlan{}'.format(vni), 'up'])
            subprocess.check_output(['ip', 'link', 'set', 'master', bridge_name, 'vxlan{}'.format(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error creating VXLAN interface for VNI {}: {}'.format(vni, e))
            raise VXLANManagerError('Error creating VXLAN interface for VNI {}'.format(vni))

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            if self.bridge_tool == 'brctl':
                subprocess.check_output(['brctl', 'delif', bridge_name, 'vxlan{}'.format(vni)])
            else:  # default to 'ip'
                subprocess.check_output(['ip', 'link', 'set', 'vxlan{}'.format(vni), 'nomaster'])

            subprocess.check_output(['ip', 'link', 'del', 'vxlan{}'.format(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error deleting VXLAN interface for VNI {}: {}'.format(vni, e))
            raise VXLANManagerError('Error deleting VXLAN interface for VNI {}'.format(vni))

    def validate_connectivity(self, src_host, dst_host, vni, port=None, timeout=3):
        port = port or self.default_dst_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)

            try:
                s.connect((dst_host, port))
                logger.info('Connectivity to VXLAN VNI {} at {}:{} from {} is successful.'.format(vni, dst_host, port, src_host))
            except socket.error as e:
                logger.error('Failed to establish connectivity to VXLAN VNI {} at {}:{} from {}: {}'.format(vni, dst_host, port, src_host, e))
                raise VXLANManagerError('Failed to establish connectivity to VXLAN VNI {} at {}:{} from {}'.format(vni, dst_host, port, src_host))

    def list_vxlan_interfaces(self, fields, output_format):
        result = subprocess.check_output(['ip', '-d', 'link', 'show', 'type', 'vxlan'], text=True)
        vxlan_interfaces = []

        vxlan_regex = re.compile(r'(?P<ifname>\S+): .+ vxlan id (?P<vni>\d+) .+ '
                                 r'local (?P<src_host>\S+) remote (?P<dst_host>\S+|\d+\.\d+\.\d+\.\d+) '
                                 r'.+ dstport (?P<dst_port>\d+)')

        for line in result.split('\n'):
            match = vxlan_regex.search(line)
            if match:
                details = match.groupdict()
                vxlan_details = {key: value for key, value in details.items() if fields == 'all' or key in fields}
                vxlan_interfaces.append(vxlan_details)

        return OutputFormatter.format(vxlan_interfaces, output_format)

class OutputFormatter:
    @staticmethod
    def format(data, format_type):
        if format_type == 'json':
            return json.dumps(data, indent=2)
        elif format_type == 'xml':
            root = ElementTree.Element('VXLANInterfaces')
            for item in data:
                interface_element = ElementTree.SubElement(root, 'Interface')
                for key, value in item.items():
                    child = ElementTree.SubElement(interface_element, key)
                    child.text = value
            return ElementTree.tostring(root)
        elif format_type == 'csv':
            output = io.BytesIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()
        elif format_type == 'script':
            return '\n'.join('{}: {}'.format(key, value) for item in data for key, value in item.items())
        elif format_type == 'table':
            header = ' | '.join(data[0].keys())
            rows = [' | '.join(item.values()) for item in data]
            return '\n'.join([header] + rows)
        else:
            raise ValueError('Invalid format type: {}'.format(format_type))

def main():
    parser = argparse.ArgumentParser(description='Manage VXLAN interfaces')
    parser.add_argument('--vni', type=int, help='VXLAN Network Identifier (VNI)')
    parser.add_argument('--src-host', help='Source host IP address')
    parser.add_argument('--dst-host', help='Destination host IP address')
    parser.add_argument('--bridge-name', help='Bridge name')
    parser.add_argument('--src-port', type=int, help='Source port')
    parser.add_argument('--dst-port', type=int, help='Destination port')
    parser.add_argument('--dev', help='Parent interface for the VXLAN')
    parser.add_argument('--fields', nargs='+', default='all', help='Fields to display when listing VXLAN interfaces')
    parser.add_argument('--format', choices=['json', 'xml', 'csv', 'script', 'table'], default='table', help='Output format for listing VXLAN interfaces')
    parser.add_argument('--action', choices=['create', 'cleanup', 'validate', 'list'], required=True, help='Action to perform: create, cleanup, validate, or list VXLAN interfaces')

    args = parser.parse_args()

    vxlan_manager = VXLANManager()

    try:
        if args.action == 'create':
            vxlan_manager.create_vxlan_interface(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.dst_port, args.dev)
        elif args.action == 'cleanup':
            vxlan_manager.cleanup_vxlan_interface(args.vni, args.bridge_name)
        elif args.action == 'validate':
            vxlan_manager.validate_connectivity(args.src_host, args.dst_host, args.vni, args.dst_port)
        elif args.action == 'list':
            output = vxlan_manager.list_vxlan_interfaces(args.fields, args.format)
            print output
    except VXLANManagerError as e:
        logger.error(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
