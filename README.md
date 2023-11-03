# Tunnel Manager

The Tunnel Manager is a Python script for managing VXLAN and GENEVE tunnels between bridges. It provides functionality for creating, cleaning up, validating, and listing tunnel interfaces.

## Features

- Supports both VXLAN and GENEVE tunnel types.
- Create and manage tunnel interfaces between bridges.
- Validate connectivity between source and destination hosts.
- List existing tunnel interfaces.

## Prerequisites

Before using the Tunnel Manager, ensure you have the following prerequisites installed:

- Python 3
- Required Python packages (can be installed via pip):
  - argparse
  - logging
  - socket
  - subprocess
  - sys
  - yaml
  - json
  - csv
  - xml.etree.ElementTree (standard library)

## Usage

```bash
python tunnel_manager.py --action <action> [options]
```

## Actions
* create: Create a tunnel interface.
* cleanup: Cleanup a tunnel interface.
* validate: Validate connectivity between hosts.
* list: List existing tunnel interfaces.

## Options
* --tunnel-type: Type of tunnel to create (default: vxlan).
* --vni: Tunnel Network Identifier (VNI).
* --src-host: Source host IP address.
* --dst-host: Destination host IP address.
* --bridge-name: Bridge name.
* --src-port: Source port.
* --dev: Parent interface for the tunnel.
* --fields: Fields to display when listing tunnel interfaces (default: all).
* --format: Output format for listing tunnel interfaces (default: table).
* --action: Action to perform (create, cleanup, validate, or list tunnel interfaces).

## Examples
### Create a VXLAN tunnel interface:
```
python tunnel_manager.py --action create --tunnel-type vxlan --vni 100 --src-host 192.168.1.1 --dst-host 192.168.1.2 --bridge-name br0
```

### List existing tunnel interfaces in JSON format:
```
python tunnel_manager.py --action list --format json
```

## License
This project is licensed under the GPL License - see the LICENSE file for details.

## Author
Ofer Chen
