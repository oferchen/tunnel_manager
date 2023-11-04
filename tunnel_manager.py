import argparse
import csv
import json
import logging
import socket
import subprocess
import sys
from xml.etree import ElementTree

import yaml

# Configure logging with timestamps
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TunnelManagerError(Exception):
    """Custom exception for Tunnel Manager errors."""

    pass


class TunnelManager:
    def __init__(self, tunnel_type, bridge_tool="ip"):
        self.tunnel_type = tunnel_type
        self.bridge_tool = bridge_tool

    def create_tunnel_interface(self, vni, src_host, dst_host, bridge_name, src_port=None, dst_port=None, dev="eth0"):
        src_port = src_port or 4789  # Default source port for both VXLAN and GENEVE
        dst_port = dst_port or 4789  # Default destination port for VXLAN, 6081 for GENEVE

        try:
            subprocess.run(["ip", "link", "add", f"{self.tunnel_type}{vni}", "type", self.tunnel_type, "id", str(vni), "local", src_host, "remote", dst_host, "dev", dev, "dstport", str(dst_port)], check=True)
            subprocess.run(["ip", "link", "set", f"{self.tunnel_type}{vni}", "up"], check=True)
            subprocess.run(["ip", "link", "set", "master", bridge_name, f"{self.tunnel_type}{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating {self.tunnel_type.upper()} interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error creating {self.tunnel_type.upper()} interface for VNI {vni}") from e

    def cleanup_tunnel_interface(self, vni, bridge_name):
        try:
            if self.bridge_tool == "brctl":
                subprocess.run(["brctl", "delif", bridge_name, f"{self.tunnel_type}{vni}"], check=True)
            else:  # Default to 'ip'
                subprocess.run(["ip", "link", "set", f"{self.tunnel_type}{vni}", "nomaster"], check=True)

            subprocess.run(["ip", "link", "del", f"{self.tunnel_type}{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deleting {self.tunnel_type.upper()} interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error deleting {self.tunnel_type.upper()} interface for VNI {vni}") from e

    def validate_connectivity(self, src_host, dst_host, vni, port=None, timeout=3, max_retries=3):
        src_port = port or 4789  # Default source port for both VXLAN and GENEVE

        retries = 0
        while retries < max_retries:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)

                try:
                    s.connect((dst_host, src_port))
                    logger.info(f"Connectivity to {self.tunnel_type.upper()} VNI {vni} at {dst_host}:{src_port} from {src_host} is successful.")
                    return
                except socket.error as e:
                    retries += 1
                    logger.warning(f"Retry {retries}/{max_retries} - Failed to establish connectivity to {self.tunnel_type.upper()} VNI {vni} at {dst_host}:{src_port} from {src_host}: {e}")
                    if retries == max_retries:
                        logger.error(f"Failed to establish connectivity to {self.tunnel_type.upper()} VNI {vni} at {dst_host}:{src_port} from {src_host} after {max_retries} attempts.")
                        raise TunnelManagerError(f"Failed to establish connectivity to {self.tunnel_type.upper()} VNI {vni} at {dst_host}:{src_port} from {src_host}") from e

    def collect_tunnel_data(self):
        tunnel_data = []
        if self.tunnel_type == "vxlan":
            tunnel_data = self.collect_vxlan_data()
        elif self.tunnel_type == "geneve":
            tunnel_data = self.collect_geneve_data()
        return tunnel_data

    def collect_vxlan_data(self):
        vxlan_data = []
        try:
            result = subprocess.run(["ip", "-d", "link", "show", "type", "vxlan"], stdout=subprocess.PIPE, text=True)
            vxlan_regex = re.compile(r"(?P<ifname>\S+): .+ vxlan id (?P<vni>\d+) .+ " r"local (?P<src_host>\S+) remote (?P<dst_host>\S+|\d+\.\d+\.\d+\.\d+) " r".+ dstport (?P<dst_port>\d+)")

            for line in result.stdout.split("\n"):
                match = vxlan_regex.search(line)
                if match:
                    details = match.groupdict()
                    vxlan_details = dict(details.items())
                    vxlan_data.append(vxlan_details)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error collecting VXLAN tunnel data: {e}")

        return vxlan_data

    def collect_geneve_data(self):
        geneve_data = []
        try:
            result = subprocess.run(["ip", "-d", "link", "show", "type", "geneve"], stdout=subprocess.PIPE, text=True)
            geneve_regex = re.compile(r"(?P<ifname>\S+): .+ geneve id (?P<vni>\d+) .+ " r"local (?P<src_host>\S+) remote (?P<dst_host>\S+|\d+\.\d+\.\d+\.\d+) " r".+ dstport (?P<dst_port>\d+)")

            for line in result.stdout.split("\n"):
                match = geneve_regex.search(line)
                if match:
                    details = match.groupdict()
                    geneve_details = dict(details.items())
                    geneve_data.append(geneve_details)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error collecting GENEVE tunnel data: {e}")

        return geneve_data


class OutputFormatter:
    @staticmethod
    def format(data, format_type):
        if format_type == "json":
            return json.dumps(data, indent=2)
        elif format_type == "yaml":
            return yaml.dump(data, default_flow_style=False)
        elif format_type == "xml":
            root = ElementTree.Element("TunnelInterfaces")
            for item in data:
                interface_element = ElementTree.SubElement(root, "Interface")
                for key, value in item.items():
                    element = ElementTree.SubElement(interface_element, key)
                    element.text = str(value)
            return ElementTree.tostring(root, encoding="unicode")
        elif format_type == "csv":
            if not data:
                return ""
            csv_output = io.StringIO()
            writer = csv.DictWriter(csv_output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            return csv_output.getvalue()
        elif format_type == "script":
            return ", ".join([": ".join([key, str(val)]) for item in data for key, val in item.items()])
        elif format_type == "table":
            table = str()
            headers = data[0].keys() if data else []
            table += " | ".join(headers) + "\n"
            table += "-+-".join(["-" * len(header) for header in headers]) + "\n"
            for item in data:
                table += " | ".join(item.values()) + "\n"
            return table


def main():
    parser = argparse.ArgumentParser(description="Manage VXLAN and GENEVE tunnels between bridges.")
    parser.add_argument("--tunnel-type", choices=["vxlan", "geneve"], default="vxlan", help="Type of tunnel to create (default: vxlan)")
    parser.add_argument("--vni", type=int, help="Tunnel Network Identifier (VNI)")
    parser.add_argument("--src-host", help="Source host IP address")
    parser.add_argument("--dst-host", help="Destination host IP address")
    parser.add_argument("--bridge-name", help="Bridge name")
    parser.add_argument("--src-port", type=int, help="Source port")
    parser.add_argument("--dev", help="Parent interface for the tunnel")
    parser.add_argument("--fields", nargs="+", default="all", help="Fields to display when listing tunnel interfaces")
    parser.add_argument("--format", choices=["json", "yaml", "xml", "csv", "script", "table"], default="table", help="Output format for listing tunnel interfaces")
    parser.add_argument("--action", choices=["create", "cleanup", "validate", "list"], required=True, help="Action to perform: create, cleanup, validate, or list tunnel interfaces")

    args = parser.parse_args()

    tunnel_manager = TunnelManager(args.tunnel_type)

    try:
        if args.action == "create":
            tunnel_manager.create_tunnel_interface(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.src_port, args.dev)
        elif args.action == "cleanup":
            tunnel_manager.cleanup_tunnel_interface(args.vni, args.bridge_name)
        elif args.action == "validate":
            tunnel_manager.validate_connectivity(args.src_host, args.dst_host, args.vni, args.src_port)
        elif args.action == "list":
            tunnel_data = tunnel_manager.collect_tunnel_data()
            output = OutputFormatter.format(tunnel_data, args.format)
            print(output)
    except TunnelManagerError as e:
        logger.error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
