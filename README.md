# VXLAN Management

## Description

The VXLAN Management is a Python script that allows you to create and manage VXLAN tunnels between two network bridges. It simplifies the process of setting up VXLAN tunnels for virtual network overlays.

## Features

1. Create VXLAN tunnels between two bridges.
2. Remove existing VXLAN tunnels.
3. Support for both IPv4 and IPv6 addresses.
4. Optional post-deployment connectivity validation.
5. Basic error handling and logging.

## Requirements

- Python 2.7 (for Python 2 compatibility) or Python 3.6+
- Linux-based operating system
- `brctl` and `ip` command-line utilities

## Usage

### Installation

#### 1. Clone this repository or download the script.

```bash
git clone https://github.com/yourusername/vxlan-management-script.git
cd vxlan-management-script
```

#### 2. Install any required Python packages (if needed).
```
pip install -r requirements.txt
python vxlan_manager.py [OPTIONS]
```

### Options:

* --vni VNI: VXLAN VNI (required).
* --src-host SRC_HOST: Source host IP address (required).
* --dst-host DST_HOST: Destination host IP address (required).
* --bridge-name BRIDGE_NAME: Bridge name to add VXLAN interface (required).
* --src-port SRC_PORT: Source VXLAN UDP port (default: 4789).
* --dst-port DST_PORT: Destination VXLAN UDP port (default: 4789).
* --dev NETWORK_DEVICE: Network device to utilize (default: eth0).
* --cleanup: Remove VXLAN tunnel instead of creating it (optional).
* --validate-connectivity: Perform post-deployment connectivity validation (optional).
* --bridge-tool TOOL: Bridge management tool to use either ip or brctl (default: ip).

#### Examples
* Create a VXLAN tunnel:
```
python vxlan_manager.py --vni 1001 --src-host 192.168.1.1 --dst-host 192.168.1.2 --bridge-name br0
```

* Create a VXLAN tunnel with custom ports:
```
python vxlan_manager.py --vni 1001 --src-host 192.168.1.1 --dst-host 192.168.1.2 --bridge-name br0 --src-port 5000 --dst-port 6000
```
* Remove an existing VXLAN tunnel:
```
python vxlan_manager.py --vni 1001 --bridge-name br0 --cleanup
```

**License
This script is licensed under the GPL License. See the LICENSE file for details.**

