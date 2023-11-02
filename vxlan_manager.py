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
            subprocess.run(['ip', 'link', 'add', f'vxlan{vni}', 'type', 'vxlan',
                            'id', str(vni),
                            'local', src_host,
                            'remote', dst_host,
                            'dev', dev,
                            'dstport', str(dst_port)], check=True)
            subprocess.run(['ip', 'link', 'set', f'vxlan{vni}', 'up'], check=True)
            subprocess.run(['ip', 'link', 'set', 'master', bridge_name, f'vxlan{vni}'], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f'Error creating VXLAN interface for VNI {vni}: {e}')
            raise VXLANManagerError(f'Error creating VXLAN interface for VNI {vni}') from e

    def cleanup_vxlan_interface(self, vni, bridge_name):
        try:
            if self.bridge_tool == 'brctl':
                subprocess.run(['brctl', 'delif', bridge_name, f'vxlan{vni}'], check=True)
            else:  # default to 'ip'
                subprocess.run(['ip', 'link', 'set', f'vxlan{vni}', 'nomaster'], check=True)

            subprocess.run(['ip', 'link', 'del', f'vxlan{vni}'], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f'Error deleting VXLAN interface for VNI {vni}: {e}')
            raise VXLANManagerError(f'Error deleting VXLAN interface for VNI {vni}') from e

    def validate_connectivity(self, src_host, dst_host, vni, port=None, timeout=3, max_retries=3):
        port = port or self.default_src_port
        retries = 0
        while retries < max_retries:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)

                try:
                    s.connect((dst_host, port))
                    logger.info(f'Connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host} is successful.')
                    return
                except socket.error as e:
                    retries += 1
                    logger.warning(f'Retry {retries}/{max_retries} - Failed to establish connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host}: {e}')
                    if retries == max_retries:
                        logger.error(f'Failed to establish connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host} after {max_retries} attempts.')
                        raise VXLANManagerError(f'Failed to establish connectivity to VXLAN VNI {vni} at {dst_host}:{port} from {src_host}') from e

    def list_vxlan_interfaces(self, fields, output_format):
        result = subprocess.run(['ip', '-d', 'link', 'show', 'type', 'vxlan'], stdout=subprocess.PIPE, text=True)
        vxlan_interfaces = []

        vxlan_regex = re.compile(r'(?P<ifname>\S+): .+ vxlan id (?P<vni>\d+) .+ '
                                 r'local (?P<src_host>\S+) remote (?P<dst_host>\S+|\d+\.\d+\.\d+\.\d+) '
                                 r'.+ dstport (?P<dst_port>\d+)')

        for line in result.stdout.split('\n'):
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
            return ElementTree.tostring(root, encoding='unicode')
        elif format_type == 'csv':
            output = io.StringIO()
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
