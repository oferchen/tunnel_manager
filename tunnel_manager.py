import argparse
import csv
import io
import json
import logging
import re
import shutil
import socket
import subprocess
import sys
from enum import Enum
from os import PathLike
from typing import Any, Dict, List, Optional, Protocol, Union
from xml.etree import ElementTree

import yaml

# Configure logging with timestamps
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


CmdArg = Union[str, bytes, PathLike]

class CommandBuilder:
    """Builder for safely constructing shell command arguments."""
    def __init__(self) -> None:
        self._cmd: List[CmdArg] = []

    def add(self, *args: Optional[CmdArg]) -> "CommandBuilder":
        for arg in args:
            if arg is not None:
                self._cmd.append(arg)
        return self

    def extend(self, args: List[Optional[CmdArg]]) -> "CommandBuilder":
        for arg in args:
            if arg is not None:
                self._cmd.append(arg)
        return self

    def build(self) -> List[CmdArg]:
        return self._cmd.copy()

class TunnelManagerError(Exception):
    """Custom exception for Tunnel Manager errors."""

    pass


# Global regex pattern for IP matching, shared by tunnel implementations
IP_PATTERN: str = r"(?:\d{1,3}(?:\.\d{1,3}){3}|[a-fA-F0-9:]+(?::\d{1,3}(?:\.\d{1,3}){3})?)"

class TunnelInterface(Protocol):
    def create_tunnel_interface(
        self,
        vni: int,
        src_host: str,
        dst_host: str,
        bridge_name: str,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None,
        dev: Optional[str] = "eth0"
    ) -> None:
        ...

    def cleanup_tunnel_interface(
        self,
        vni: int,
        bridge_name: str
    ) -> None:
        ...

    def validate_connectivity(
        self,
        src_host: str,
        dst_host: str,
        vni: int,
        port: Optional[int] = None,
        timeout: int = 3,
        max_retries: int = 3
    ) -> None:
        ...

    def collect_tunnel_data(self) -> List[Dict[str, Any]]:
        ...


# VXLAN-specific tunnel
class VXLANTunnel(TunnelInterface):
    DEFAULT_PORT = 4789

    def __init__(self, bridge_tool: str = "ip") -> None:
        self.bridge_tool = bridge_tool
        self.tunnel_type = "vxlan"

    def create_tunnel_interface(
        self,
        vni: int,
        src_host: str,
        dst_host: str,
        bridge_name: str,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None,
        dev: Optional[str] = None
    ) -> None:
        src_port = src_port or self.DEFAULT_PORT
        dst_port = dst_port or self.DEFAULT_PORT

        try:
            builder = (
                CommandBuilder()
                .add("ip", "link", "add", f"vxlan{vni}", "type", "vxlan")
                .add("id", str(vni), "local", src_host, "remote", dst_host)
                .add("dstport", str(dst_port))
            )

            if dev:
                builder.add("dev", dev)

            cmd = builder.build()

            subprocess.run(cmd, check=True)
            subprocess.run(["ip", "link", "set", f"vxlan{vni}", "up"], check=True)
            subprocess.run(["ip", "link", "set", f"vxlan{vni}", "master", bridge_name], check=True)
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

    def validate_connectivity(
        self,
        src_host: str,
        dst_host: str,
        vni: int,
        port: Optional[int] = None,
        timeout: int = 3,
        max_retries: int = 3
    ) -> None:
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
            result = subprocess.run(["ip", "-d", "link", "show", "type", "vxlan"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

            lines = result.stdout.splitlines()
            current: Dict[str, Any] = {}

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if re.match(r"^\d+:\s+\S+: <", line):
                    if current:
                        vxlan_data.append(current)
                        current = {}
                    ifname = line.split(":")[1].strip()
                    current["ifname"] = ifname

                elif "vxlan id" in line:
                    id_match = re.search(r"vxlan id\s+(\d+)", line)
                    remote_match = re.search(r"remote\s+(" + IP_PATTERN + ")", line)
                    local_match = re.search(r"local\s+(" + IP_PATTERN + ")", line)
                    dstport_match = re.search(r"dstport\s+(\d+)", line)

                    if id_match:
                        current["vni"] = id_match.group(1)
                    if remote_match:
                        current["dst_host"] = remote_match.group(1)
                    if local_match:
                        current["src_host"] = local_match.group(1)
                    if dstport_match:
                        current["dst_port"] = dstport_match.group(1)

            if current:
                vxlan_data.append(current)

        except subprocess.CalledProcessError as e:
            logger.error(f"Error collecting VXLAN tunnel data: {e}")

        return vxlan_data

# Geneve-specific tunnel
class GeneveTunnel(TunnelInterface):
    DEFAULT_PORT = 6081

    def __init__(self, bridge_tool: str = "ip") -> None:
        self.bridge_tool = bridge_tool
        self.tunnel_type = "geneve"

    def create_tunnel_interface(
        self,
        vni: int,
        src_host: str,
        dst_host: str,
        bridge_name: str,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None,
        dev: Optional[str] = "eth0"
    ) -> None:
        src_port = src_port or self.DEFAULT_PORT
        dst_port = dst_port or self.DEFAULT_PORT

        try:
            cmd = (
                CommandBuilder()
                .add("ip", "link", "add", f"geneve{vni}", "type", "geneve")
                .add("id", str(vni), "remote", dst_host, "local", src_host)
                .add("dev", dev)
                .add("dstport", str(dst_port))
                .build()
            )
            subprocess.run(cmd, check=True)
            subprocess.run(["ip", "link", "set", f"geneve{vni}", "up"], check=True)
            subprocess.run(["ip", "link", "set", f"geneve{vni}", "master", bridge_name], check=True)
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

    def validate_connectivity(
        self,
        src_host: str,
        dst_host: str,
        vni: int,
        port: Optional[int] = None,
        timeout: int = 3,
        max_retries: int = 3
    ) -> None:
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
        geneve_data = []
        try:
            result = subprocess.run(["ip", "-d", "link", "show", "type", "geneve"], stdout=subprocess.PIPE, text=True)
            geneve_regex = re.compile(rf"\b(?P<ifname>\S+): .+ \bgeneve\b id (?P<vni>\d+) .+ remote (?P<dst_host>{IP_PATTERN}) local (?P<src_host>{IP_PATTERN}) .+ dstport (?P<dst_port>\d+)")
            for line in result.stdout.splitlines():
                if match := geneve_regex.search(line):
                    geneve_data.append(match.groupdict())
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
    def format(self, data: Any) -> str: ...


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
        if not data:
            return ""

        headers = list(data[0].keys())
        col_widths = {
            h: max(len(h), max(len(str(row.get(h, ""))) for row in data))
            for h in headers
        }

        def format_row(row: Dict[str, Any]) -> str:
            return " | ".join(f"{str(row.get(h, '')).center(col_widths[h])}" for h in headers)

        header_line = " | ".join(h.center(col_widths[h]) for h in headers)
        separator = "-+-".join("-" * col_widths[h] for h in headers)
        rows = [format_row(row) for row in data]

        return "\n".join([header_line, separator] + rows)


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

    def validate(self, src_host: str, dst_host: str, vni: int, port: Optional[int] = None, timeout: int = 3, max_retries: int = 3) -> None:
        self.tunnel.validate_connectivity(src_host, dst_host, vni, port, timeout, max_retries)

    def list(self) -> List[Dict[str, Any]]:
        return self.tunnel.collect_tunnel_data()

    def execute_action(self, action: str, **kwargs: Any) -> Any:
        method = getattr(self, action, None)
        if callable(method):
            return method(**kwargs)
        raise ValueError(f"No method available for action: {action}")


class CommandValidator(Protocol):
    def check_command_existence(self, command: str) -> bool:
        ...

    def check_bridge_tool_existence(self, bridge_tool: str) -> None:
        ...


class SystemCommandValidator(CommandValidator):
    def check_command_existence(self, command: str) -> bool:
        return shutil.which(command) is not None

    def check_bridge_tool_existence(self, bridge_tool: str) -> None:
        if not self.check_command_existence(bridge_tool):
            raise RuntimeError(f"Error: The bridge tool '{bridge_tool}' is not found. Please install it.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage VXLAN and GENEVE tunnels between bridges.")
    parser.add_argument(
        "--tunnel-type",
        type=str,
        choices=[t.value for t in TunnelType],
        default=TunnelType.VXLAN.value,
        help="Type of tunnel to create (default: %(default)s)"
    )
    parser.add_argument("--bridge-tool", choices=["ip", "brctl"], default="ip", help="Bridge tool to use (default: %(default)s)")
    subparsers = parser.add_subparsers(dest="command", help="sub-command help")

    # CREATE
    parser_create = subparsers.add_parser("create", help="create a tunnel interface")
    parser_create.add_argument("--vni", type=int, required=True)
    parser_create.add_argument("--src-host", required=True)
    parser_create.add_argument("--dst-host", required=True)
    parser_create.add_argument("--bridge-name", required=True)
    parser_create.add_argument("--src-port", type=int)
    parser_create.add_argument("--dst-port", type=int)
    parser_create.add_argument("--dev")

    # CLEANUP
    parser_cleanup = subparsers.add_parser("cleanup", help="cleanup a tunnel interface")
    parser_cleanup.add_argument("--vni", type=int, required=True)
    parser_cleanup.add_argument("--bridge-name", required=True)

    # VALIDATE
    parser_validate = subparsers.add_parser("validate", help="validate connectivity of a tunnel interface")
    parser_validate.add_argument("--src-host", required=True)
    parser_validate.add_argument("--dst-host", required=True)
    parser_validate.add_argument("--vni", type=int, required=True)
    parser_validate.add_argument("--port", type=int)
    parser_validate.add_argument("--retries", type=int, default=3)
    parser_validate.add_argument("--timeout", type=int, default=3)

    # LIST
    parser_list = subparsers.add_parser("list", help="list all tunnel interfaces")
    parser_list.add_argument(
        "-fo", "--format",
        type=str,
        choices=[f.value for f in OutputFormatType],
        default=OutputFormatType.TABLE.value,
        help="Output format (default: %(default)s)"
    )
    parser_list.add_argument(
        "-fi", "--fields",
        nargs="+",
        default=["all"],
        help="Fields to display (default: all)"
    )

    args = parser.parse_args()
    command_validator = SystemCommandValidator()
    command_validator.check_bridge_tool_existence(args.bridge_tool)

    try:
        tunnel_type = TunnelType(args.tunnel_type)
        tunnel = TunnelFactory.create_tunnel(tunnel_type, bridge_tool=args.bridge_tool)
        manager = TunnelManager(tunnel)

        if args.command == "create":
            manager.create(args.vni, args.src_host, args.dst_host, args.bridge_name, args.src_port, args.dst_port, args.dev)
        elif args.command == "cleanup":
            manager.cleanup(args.vni, args.bridge_name)
        elif args.command == "validate":
            manager.validate(args.src_host, args.dst_host, args.vni, args.port, args.timeout, args.retries)
        elif args.command == "list":
            format_type = OutputFormatType(args.format)
            formatter = OutputFormatterFactory.get_formatter(format_type)
            data = manager.list()
            print(formatter.format(data))
        else:
            parser.print_help()
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
