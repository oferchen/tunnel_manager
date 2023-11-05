# Tunnel Manager

Tunnel Manager is a Python script for managing VXLAN and GENEVE tunnel interfaces between bridges.

## Features

- Create and manage VXLAN and GENEVE tunnel interfaces.
- Validate connectivity between tunnel endpoints.
- List all tunnel interfaces with various output formats.

## Prerequisites

Before using Tunnel Manager, ensure you have the following prerequisites installed and available on your system:

- Python 3.x
- The `ip` command-line tool (for creating and managing tunnel interfaces)
- The `brctl` command-line tool (optional, for managing bridges)

## Installation

1. Clone this repository to your local machine:

   ```bash
   git clone https://github.com/yourusername/tunnel-manager.git
   cd tunnel-manager
   ```

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
  - io
  - re
  - sys
  - enum
  - typing
  - xml.etree.ElementTree (standard library)

## Usage

```bash
python tunnel_manager.py [OPTIONS] COMMAND [ARGS]...

Options:
  --tunnel-type [vxlan|geneve]
                                  Type of tunnel to create (default: vxlan)
  -h, --help                      Show this message and exit

Commands:
  create    Create a tunnel interface
  cleanup   Cleanup a tunnel interface
  validate  Validate connectivity of a tunnel interface
  list      List all tunnel interfaces

```

## Actions

*  create    Create a tunnel interface
*  cleanup   Cleanup a tunnel interface
*  validate  Validate connectivity of a tunnel interface
*  list      List all tunnel interfaces

## Examples

###Create a VXLAN tunnel interface:
```
python tunnel_manager.py --tunnel-type vxlan create --vni 100 --src-host 10.0.0.1 --dst-host 10.0.0.2 --bridge-name br0
```

###Cleanup a VXLAN tunnel interface:
```
python tunnel_manager.py --tunnel-type vxlan cleanup --vni 100 --bridge-name br0
```

###Validate connectivity of a GENEVE tunnel interface:
```
python tunnel_manager.py --tunnel-type geneve validate --src-host 10.0.0.1 --dst-host 10.0.0.2 --vni 200 --port 6081
```

###List all tunnel interfaces in JSON format:
```
python tunnel_manager.py --tunnel-type vxlan list --format json
```

##Contributing
Contributions are welcome! If you have suggestions, feature requests, or want to report issues, please create an issue or submit a pull request.

##License
This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

## Author
Ofer Chen
