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
                interface_element = ElementTree.SubElement(root, 'Interface')
                for key, value in item.items():
                    element = ElementTree.SubElement(interface_element, key)
                    element.text = str(value)
            return ElementTree.tostring(root, encoding='unicode')
        elif format_type == 'csv':
            if not data:
                return ""
            csv_output = io.StringIO()
            writer = csv.DictWriter(csv_output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return csv_output.getvalue()
        elif format_type == 'script':
            return ', '.join([': '.join([key, str(val)]) for item in data for key, val in item.items()])
        elif format_type == 'table':
            table = str()
            headers = data[0].keys() if data else []
            table += ' | '.join(headers) + '\n'
            table += '-+-'.join(['-' * len(header) for header in headers]) + '\n'
            for item in data:
                table += ' | '.join(item.values()) + '\n'
            return table

def main():
    parser = argparse.ArgumentParser(description='Manage VXLAN tunnels between bridges.')
    parser.add_argument('--vni', type=int, help='VXLAN Network Identifier (VNI)')
    parser.add_argument('--src-host', help='Source host IP address')
    parser.add_argument('--dst-host', help='Destination host IP address')
    parser.add_argument('--bridge-name', help='Bridge name')
    parser.add_argument('--src-port', type=int, help='Source port')
    parser.add_argument('--dst-port', type=int, help='Destination port')
    parser.add_argument('--dev', help='Parent interface for the VXLAN')
    parser.add_argument('--fields', nargs='+', default='all',
                        help='Fields to display when listing VXLAN interfaces')
    parser.add_argument('--format', choices=['json', 'xml', 'csv', 'script', 'table'], default='table',
                        help='Output format for listing VXLAN interfaces')
    parser.add_argument('--action', choices=['create', 'cleanup', 'validate', 'list'], required=True,
                        help='Action to perform: create, cleanup, validate, or list VXLAN interfaces')

    args = parser.parse_args()

    vxlan_manager = VXLANManager()

    try:
        if args.action == 'create':
            vxlan_manager.create_vxlan_interface(args.vni, args.src_host, args.dst_host, args.bridge_name,
                                                 args.src_port, args.dst_port, args.dev)
        elif args.action == 'cleanup':
            vxlan_manager.cleanup_vxlan_interface(args.vni, args.bridge_name)
        elif args.action == 'validate':
            vxlan_manager.validate_connectivity(args.src_host, args.dst_host, args.vni, args.dst_port)
        elif args.action == 'list':
            output = vxlan_manager.list_vxlan_interfaces(args.fields, args.format)
            print(output)
    except VXLANManagerError as e:
        logger.error(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
