import argparse
import csv
import io
import json
import logging
import re
import socket
import subprocess
import sys
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Type
from xml.etree import ElementTree

import yaml

# Configure logging with timestamps
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TunnelManagerError(Exception):
    """Custom exception for Tunnel Manager errors."""

    pass


class TunnelInterface(Protocol):
    ip_pattern = r"(?:\d{1,3}(?:\.\d{1,3}){3}|[a-fA-F0-9:]+(?::\d{1,3}(?:\.\d{1,3}){3})?)"

    def create_tunnel_interface(self, vni: int, src_host: str, dst_host: str, bridge_name: str, src_port: Optional[int] = None, dst_port: Optional[int] = None, dev: Optional[str] = "eth0") -> None:
        raise NotImplementedError

    def cleanup_tunnel_interface(self, vni: int, bridge_name: str) -> None:
        raise NotImplementedError

    def validate_connectivity(self, src_host: str, dst_host: str, vni: int, port: Optional[int] = None, timeout: int = 3, max_retries: int = 3) -> None:
        raise NotImplementedError

    def collect_tunnel_data(self) -> List[Dict[str, Any]]:
        raise NotImplementedError


# VXLAN-specific tunnel
class VXLANTunnel(TunnelInterface):
    DEFAULT_PORT = 4789

    def __init__(self, bridge_tool: str = "ip") -> None:
        self.bridge_tool = bridge_tool
        self.tunnel_type = "vxlan"

    def create_tunnel_interface(self, vni: int, src_host: str, dst_host: str, bridge_name: str, src_port: Optional[int] = None, dst_port: Optional[int] = None, dev: Optional[str] = "eth0") -> None:
        src_port = src_port or self.DEFAULT_PORT
        dst_port = dst_port or self.DEFAULT_PORT

        try:
            subprocess.run(["ip", "link", "add", f"vxlan{vni}", "type", "vxlan", "id", str(vni), "local", src_host, "remote", dst_host, "dev", dev, "dstport", str(dst_port)], check=True)
            subprocess.run(["ip", "link", "set", f"vxlan{vni}", "up"], check=True)
            subprocess.run(["ip", "link", "set", "master", bridge_name, f"vxlan{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating VXLAN interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error creating VXLAN interface for VNI {vni}") from e

    def cleanup_tunnel_interface(self, vni: int, bridge_name: str) -> None:
        try:
            if self.bridge_tool == "brctl":
                subprocess.run(["brctl", "delif", bridge_name, f"vxlan{vni}"], check=True)
            else:
                subprocess.run(["ip", "link", "set", f"vxlan{vni}", "nomaster"], check=True)

            subprocess.run(["ip", "link", "del", f"vxlan{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deleting VXLAN interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error deleting VXLAN interface for VNI {vni}") from e

    def validate_connectivity(self, src_host: str, dst_host: str, vni: int, port: Optional[int] = None, timeout: int = 3, max_retries: int = 3) -> None:
        src_port = port or self.DEFAULT_PORT

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

    def collect_tunnel_data(self) -> List[Dict[str, Any]]:
        vxlan_data = []
        try:
            result = subprocess.run(["ip", "-d", "link", "show", "type", "vxlan"], stdout=subprocess.PIPE, text=True)
            vxlan_regex = re.compile(rf"\b(?P<ifname>\S+): .+ \bvxlan\b id (?P<vni>\d+) .+ local (?P<src_host>{self.ip_pattern}) remote (?P<dst_host>{self.ip_pattern}) .+ dstport (?P<dst_port>\d+)")

            for line in result.stdout.split("\n"):
                if match := vxlan_regex.search(line):
                    details = match.groupdict()
                    vxlan_details = dict(details.items())
                    vxlan_data.append(vxlan_details)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error collecting VXLAN tunnel data: {e}")
        return vxlan_data


# Geneve-specific tunnel
class GeneveTunnel(TunnelInterface):
    DEFAULT_PORT = 6081

    def __init__(self, bridge_tool: str = "ip") -> None:
        self.bridge_tool = bridge_tool
        self.tunnel_type = "geneve"

    def create_tunnel_interface(self, vni: int, src_host: str, dst_host: str, bridge_name: str, src_port: Optional[int] = None, dst_port: Optional[int] = None, dev: Optional[str] = "eth0") -> None:
        src_port = src_port or self.DEFAULT_PORT
        dst_port = dst_port or self.DEFAULT_PORT

        try:
            subprocess.run(["ip", "link", "add", f"geneve{vni}", "type", "geneve", "id", str(vni), "remote", dst_host, "local", src_host, "dev", dev, "dstport", str(dst_port)], check=True)
            subprocess.run(["ip", "link", "set", f"geneve{vni}", "up"], check=True)
            subprocess.run(["ip", "link", "set", "master", bridge_name, f"geneve{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating Geneve interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error creating Geneve interface for VNI {vni}") from e

    def cleanup_tunnel_interface(self, vni: int, bridge_name: str) -> None:
        try:
            if self.bridge_tool == "brctl":
                subprocess.run(["brctl", "delif", bridge_name, f"geneve{vni}"], check=True)
            else:
                subprocess.run(["ip", "link", "set", f"geneve{vni}", "nomaster"], check=True)

            subprocess.run(["ip", "link", "del", f"geneve{vni}"], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error deleting Geneve interface for VNI {vni}: {e}")
            raise TunnelManagerError(f"Error deleting Geneve interface for VNI {vni}") from e

    def validate_connectivity(self, src_host: str, dst_host: str, vni: int, port: Optional[int] = None, timeout: int = 3, max_retries: int = 3) -> None:
        src_port = port or self.DEFAULT_PORT

        retries = 0
        while retries < max_retries:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)

                try:
                    s.connect((dst_host, src_port))
                    logger.info(f"Connectivity to Geneve VNI {vni} at {dst_host}:{src_port} from {src_host} is successful.")
                    return
                except socket.error as e:
                    retries += 1
                    logger.warning(f"Retry {retries}/{max_retries} - Failed to establish connectivity to Geneve VNI {vni} at {dst_host}:{src_port} from {src_host}: {e}")
                    if retries == max_retries:
                        logger.error(f"Failed to establish connectivity to Geneve VNI {vni} at {dst_host}:{src_port} from {src_host} after {max_retries} attempts.")
                        raise TunnelManagerError(f"Failed to establish connectivity to Geneve VNI {vni} at {dst_host}:{src_port} from {src_host}") from e

    def collect_tunnel_data(self) -> List[Dict[str, Any]]:
        geneve_data = []
        try:
            result = subprocess.run(["ip", "-d", "link", "show", "type", "geneve"], stdout=subprocess.PIPE, text=True)
            geneve_regex = re.compile(rf"\b(?P<ifname>\S+): .+ \bgeneve\b id (?P<vni>\d+) .+ remote (?P<dst_host>{self.ip_pattern}) local (?P<src_host>{self.ip_pattern}) .+ dstport (?P<dst_port>\d+)")

            for line in result.stdout.split("\n"):
                if match := geneve_regex.search(line):
                    details = match.groupdict()
                    geneve_details = dict(details.items())
                    geneve_data.append(geneve_details)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error collecting Geneve tunnel data: {e}")

        return geneve_data


class TunnelType(Enum):
    VXLAN = "vxlan"
    GENEVE = "geneve"


class TunnelFactory:
    @staticmethod
    def create_tunnel(tunnel_type: TunnelType, **kwargs: Any) -> TunnelInterface:
        if tunnel_type == TunnelType.VXLAN:
            return VXLANTunnel(**kwargs)
        elif tunnel_type == TunnelType.GENEVE:
            return GeneveTunnel(**kwargs)
        else:
            raise ValueError(f"Unsupported tunnel type: {tunnel_type}")


class OutputFormatType(Enum):
    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    CSV = "csv"
    SCRIPT = "script"
    TABLE = "table"


class OutputFormatterStrategy(Protocol):
    def format(self, data: Any) -> str:
        ...


class JsonFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        return json.dumps(data, indent=2)


class YamlFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        return yaml.dump(data, default_flow_style=False)


class XmlFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        root = ElementTree.Element("TunnelInterfaces")
        for item in data:
            interface = ElementTree.SubElement(root, "Interface")
            for key, value in item.items():
                ElementTree.SubElement(interface, key).text = str(value)
        return ElementTree.tostring(root, encoding="unicode")


class CsvFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        if not data:
            return ""
        csv_output = io.StringIO()
        writer = csv.DictWriter(csv_output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return csv_output.getvalue()


class ScriptFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        return ", ".join([": ".join([key, str(val)]) for item in data for key, val in item.items()])


class TableFormatter(OutputFormatterStrategy):
    def format(self, data: Any) -> str:
        table = str()
        headers = data[0].keys() if data else []
        table += " | ".join(str(item.get(header, "")) for header in headers) + "\n"
        table += "-+-".join(["-" * len(header) for header in headers]) + "\n"
        for item in data:
            table += " | ".join(item.values()) + "\n"
        return table


class OutputFormatterFactory:
    formatters = {OutputFormatType.JSON: JsonFormatter(), OutputFormatType.YAML: YamlFormatter(), OutputFormatType.XML: XmlFormatter(), OutputFormatType.CSV: CsvFormatter(), OutputFormatType.SCRIPT: ScriptFormatter(), OutputFormatType.TABLE: TableFormatter()}

    @staticmethod
    def get_formatter(format_type: OutputFormatType) -> OutputFormatterStrategy:
        return OutputFormatterFactory.formatters[format_type]


class TunnelManager:
    def __init__(self, tunnel: TunnelInterface) -> None:
        self.tunnel: TunnelInterface = tunnel

    def create(self, vni: int, src_host: str, dst_host: str, bridge_name: str, src_port: Optional[int] = None, dst_port: Optional[int] = None, dev: Optional[str] = None) -> None:
        self.tunnel.create_tunnel_interface(vni, src_host, dst_host, bridge_name, src_port, dst_port, dev)

    def cleanup(self, vni: int, bridge_name: str) -> None:
        self.tunnel.cleanup_tunnel_interface(vni, bridge_name)

    def validate(self, src_host: str, dst_host: str, vni: int, port: Optional[int] = None) -> None:
        self.tunnel.validate_connectivity(src_host, dst_host, vni, port)

    def list(self) -> List[Dict[str, Any]]:
        return self.tunnel.collect_tunnel_data()

    def execute_action(self, action: str, **kwargs: Any) -> Any:
        if method := getattr(self, action):
            return method(**kwargs)
        raise ValueError(f"No method available for action: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage VXLAN and GENEVE tunnels between bridges.")
    parser.add_argument("--tunnel-type", type=TunnelType, choices=[tunnel_type.value for tunnel_type in TunnelType], default=TunnelType.VXLAN.value, help="Type of tunnel to create (default: %(default)s)")
    subparsers = parser.add_subparsers(dest="command", help="sub-command help")

    # Create the parser for the "create" command
    parser_create = subparsers.add_parser("create", help="create a tunnel interface")
    parser_create.add_argument("--vni", type=int, required=True, help="VNI (Virtual Network Identifier)")
    parser_create.add_argument("--src-host", required=True, help="Source host IP address")
    parser_create.add_argument("--dst-host", required=True, help="Destination host IP address")
    parser_create.add_argument("--bridge-name", required=True, help="Bridge name to associate with the tunnel interface")
    parser_create.add_argument("--src-port", type=int, help="Source port (optional)")
    parser_create.add_argument("--dst-port", type=int, help="Destination port (optional)")
    parser_create.add_argument("--dev", help="Device (optional)")

    # Create the parser for the "cleanup" command
    parser_cleanup = subparsers.add_parser("cleanup", help="cleanup a tunnel interface")
    parser_cleanup.add_argument("--vni", type=int, required=True, help="VNI (Virtual Network Identifier)")
    parser_cleanup.add_argument("--bridge-name", required=True, help="Bridge name associated with the tunnel interface")

    # Create the parser for the "validate" command
    parser_validate = subparsers.add_parser("validate", help="validate connectivity of a tunnel interface")
    parser_validate.add_argument("--src-host", required=True, help="Source host IP address")
    parser_validate.add_argument("--dst-host", required=True, help="Destination host IP address")
    parser_validate.add_argument("--vni", type=int, required=True, help="VNI (Virtual Network Identifier)")
    parser_validate.add_argument("--port", type=int, help="Port (optional)")
    parser_validate.add_argument("--retries", type=int, default=3, help="Number of retries for connectivity validation (default: %(default)s)")
    parser_validate.add_argument("--timeout", type=int, default=3, help="Timeout in seconds for connectivity validation (default: %(default)s)")

    # Create the parser for the "list" command
    parser_list = subparsers.add_parser("list", help="list all tunnel interfaces")
    parser_list.add_argument("-fo", "--format", type=OutputFormatType, choices=[format_type.value for format_type in OutputFormatType], default=OutputFormatType.TABLE, help="Output format for listing tunnels (default: %(default)s)")
    parser_list.add_argument("-fi", "--fields", nargs="+", default="all", help="Fields to display for listing tunnel interfaces")

    # Parse the arguments
    args = parser.parse_args()

    try:
        tunnel = TunnelFactory.create_tunnel(args.tunnel_type)
        manager = TunnelManager(tunnel)
        if args.command == "create":
            manager.create(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.dst_port, args.dev)
        elif args.command == "cleanup":
            manager.cleanup(args.vni, args.bridge_name)
        elif args.command == "validate":
            manager.validate(args.src_host, args.dst_host, args.vni, args.src_port or args.dst_port, args.timeout, args.retries)
        elif args.command == "list":
            data = manager.list()
            formatter = OutputFormatterFactory.get_formatter(args.output_format)
            print(formatter.format(data))
        else:
            parser.print_help()
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
