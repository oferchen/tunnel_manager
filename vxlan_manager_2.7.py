from __future__ import print_function

import argparse
import logging
import socket
import subprocess
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
            # Determine IP version (IPv4 or IPv6) based on the address format
            ip_version = socket.AF_INET if '.' in src_host else socket.AF_INET6

            subprocess.call(['ip', '-{}'.format(ip_version), 'link', 'add', 'vxlan' + str(vni), 'type', 'vxlan',
                            'id', str(vni),
                            'local', src_host,
                            'remote', dst_host,
                            'dev', 'eth0',
                            'dstport', str(src_port)])
            subprocess.call(['ip', '-{}'.format(ip_version), 'link', 'set', 'vxlan' + str(vni), 'up'])
            subprocess.call(['brctl', 'addif', bridge_name, 'vxlan' + str(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error creating VXLAN interface: {}'.format(e))
            sys.exit(1)

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            subprocess.call(['brctl', 'delif', bridge_name, 'vxlan' + str(vni)])
            subprocess.call(['ip', 'link', 'del', 'vxlan' + str(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error deleting VXLAN interface: {}'.format(e))
            sys.exit(1)

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            subprocess.call(['brctl', 'delif', bridge_name, 'vxlan' + str(vni)])
            subprocess.call(['ip', 'link', 'del', 'vxlan' + str(vni)])
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
            subprocess.check_call(['ip', 'link', 'add', 'vxlan{}'.format(vni), 'type', 'vxlan',
                                   'id', str(vni),
                                   'local', src_host,
                                   'remote', dst_host,
                                   'dev', dev,
                                   'dstport', str(dst_port)])
            subprocess.check_call(['ip', 'link', 'set', 'vxlan{}'.format(vni), 'up'])
            subprocess.check_call(['ip', 'link', 'set', 'master', bridge_name, 'vxlan{}'.format(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error creating VXLAN interface for VNI {}: {}'.format(vni, e))
            raise VXLANManagerError('Error creating VXLAN interface for VNI {}'.format(vni))

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            if self.bridge_tool == 'brctl':
                subprocess.check_call(['brctl', 'delif', bridge_name, 'vxlan{}'.format(vni)])
            else:  # default to 'ip'
                subprocess.check_call(['ip', 'link', 'set', 'vxlan{}'.format(vni), 'nomaster'])

            subprocess.check_call(['ip', 'link', 'del', 'vxlan{}'.format(vni)])
        except subprocess.CalledProcessError as e:
            logger.error('Error deleting VXLAN interface for VNI {}: {}'.format(vni, e))
            raise VXLANManagerError('Error deleting VXLAN interface for VNI {}'.format(vni))

    def validate_connectivity(self, src_host, dst_host, vni, port=None, timeout=3, max_retries=3):
        port = port or self.default_src_port
        retries = 0
        while retries < max_retries:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)

            try:
                s.connect((dst_host, port))
                logger.info('Connectivity to VXLAN VNI {} at {}:{} from {} is successful.'.format(vni, dst_host, port, src_host))
                s.close()
                return
            except socket.error as e:
                retries += 1
                logger.warning('Retry {}/{} - Failed to establish connectivity to VXLAN VNI {} at {}:{} from {}: {}'.format(retries, max_retries, vni, dst_host, port, src_host, e))
                s.close()
                if retries == max_retries:
                    logger.error('Failed to establish connectivity to VXLAN VNI {} at {}:{} from {} after {} attempts.'.format(vni, dst_host, port, src_host, max_retries))
                    raise VXLANManagerError('Failed to establish connectivity to VXLAN VNI {} at {}:{} from {}'.format(vni, dst_host, port, src_host))

    def list_vxlan_interfaces(self, fields, output_format):
        result = subprocess.Popen(['ip', '-d', 'link', 'show', 'type', 'vxlan'], stdout=subprocess.PIPE, text=True)
        stdout, _ = result.communicate()
        vxlan_interfaces = []

        vxlan_regex = re.compile(r'(?P<ifname>\S+): .+ vxlan id (?P<vni>\d+) .+ '
                                 r'local (?P<src_host>\S+) remote (?P<dst_host>\S+|\d+\.\d+\.\d+\.\d+) '
                                 r'.+ dstport (?P<dst_port>\d+)')

        for line in stdout.split('\n'):
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
                entry = ElementTree.SubElement(root, 'VXLANInterface')
                for key, value in item.items():
                    element = ElementTree.SubElement(entry, key)
                    element.text = value
            return ElementTree.tostring(root, encoding='us-ascii')
        elif format_type == 'csv':
            output = io.BytesIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return output.getvalue()
        else:  # default to 'table'
            headers = data[0].keys()
            rows = [x.values() for x in data]
            return '\n'.join(['\t'.join(headers)] + ['\t'.join(map(str, row)) for row in rows])

def main():
    parser = argparse.ArgumentParser(description='Manage VXLAN interfaces.')
    parser.add_argument('action', choices=['create', 'delete', 'validate', 'list'], help='Action to perform')
    parser.add_argument('--vni', type=int, help='VNI for the VXLAN interface')
    parser.add_argument('--src_host', help='Source host IP address')
    parser.add_argument('--dst_host', help='Destination host IP address')
    parser.add_argument('--bridge_name', help='Name of the bridge to attach the VXLAN interface to')
    parser.add_argument('--src_port', type=int, default=4789, help='Source port (default: 4789)')
    parser.add_argument('--dst_port', type=int, default=4789, help='Destination port (default: 4789)')
    parser.add_argument('--dev', default='eth0', help='Physical device to bind to (default: eth0)')
    parser.add_argument('--fields', default='all', nargs='+', help='Fields to display when listing interfaces')
    parser.add_argument('--output_format', default='table', choices=['json', 'xml', 'csv', 'table'],
                        help='Output format for listing interfaces')
    parser.add_argument('--timeout', type=int, default=3, help='Timeout in seconds for validating connectivity')
    parser.add_argument('--max_retries', type=int, default=3, help='Maximum number of retries for validating connectivity')
    args = parser.parse_args()

    vxlan_manager = VXLANManager()

    if args.action == 'create':
        vxlan_manager.create_vxlan_interface(args.vni, args.src_host, args.dst_host, args.bridge_name,
                                             args.src_port, args.dst_port, args.dev)
    elif args.action == 'delete':
        vxlan_manager.cleanup_vxlan_interface(args.vni, args.bridge_name)
    elif args.action == 'validate':
        vxlan_manager.validate_connectivity(args.src_host, args.dst_host, args.vni, args.src_port,
                                            args.timeout, args.max_retries)
    elif args.action == 'list':
        output = vxlan_manager.list_vxlan_interfaces(args.fields, args.output_format)
        print(output)

if __name__ == '__main__':
    main()
