# File: test_vxlan_manager.py

import unittest
from unittest.mock import MagicMock, mock_open, patch

from vxlan_manager import OutputFormatter, VXLANManager, VXLANManagerError


class TestVXLANManager(unittest.TestCase):

    def setUp(self):
        self.vxlan_manager = VXLANManager()

    @patch('vxlan_manager.subprocess.run')
    def test_create_vxlan_interface_success(self, mock_run):
        self.vxlan_manager.create_vxlan_interface(1001, '192.168.1.1', '192.168.1.2', 'br0')
        mock_run.assert_called()

    @patch('vxlan_manager.subprocess.run')
    def test_create_vxlan_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'ip')
        with self.assertRaises(VXLANManagerError):
            self.vxlan_manager.create_vxlan_interface(1001, '192.168.1.1', '192.168.1.2', 'br0')

    @patch('vxlan_manager.subprocess.run')
    def test_cleanup_vxlan_interface_success(self, mock_run):
        self.vxlan_manager.cleanup_vxlan_interface(1001, 'br0')
        mock_run.assert_called()

    @patch('vxlan_manager.subprocess.run')
    def test_cleanup_vxlan_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'ip')
        with self.assertRaises(VXLANManagerError):
            self.vxlan_manager.cleanup_vxlan_interface(1001, 'br0')

    @patch('vxlan_manager.socket.socket')
    def test_validate_connectivity_success(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        self.vxlan_manager.validate_connectivity('192.168.1.1', '192.168.1.2', 1001)
        mock_socket_instance.connect.assert_called_with(('192.168.1.2', 4789))

    @patch('vxlan_manager.socket.socket')
    def test_validate_connectivity_failure(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        mock_socket_instance.connect.side_effect = socket.error
        with self.assertRaises(VXLANManagerError):
            self.vxlan_manager.validate_connectivity('192.168.1.1', '192.168.1.2', 1001)

    @patch('vxlan_manager.subprocess.run')
    def test_list_vxlan_interfaces(self, mock_run):
        mock_run.return_value.stdout = 'vxlan1001: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n' \
                                       '    vxlan id 1001 local 192.168.1.1 remote 192.168.1.2 dstport 4789'
        result = self.vxlan_manager.list_vxlan_interfaces(['vni', 'src_host', 'dst_host'], 'table')
        self.assertIn('vxlan1001', result)
        self.assertIn('192.168.1.1', result)
        self.assertIn('192.168.1.2', result)

class TestOutputFormatter(unittest.TestCase):

    def test_format_json(self):
        data = [{"key1": "value1", "key2": "value2"}]
        result = OutputFormatter.format(data, 'json')
        self.assertEqual(json.loads(result), data)

    def test_format_xml(self):
        data = [{"key1": "value1", "key2": "value2"}]
        result = OutputFormatter.format(data, 'xml')
        root = ElementTree.fromstring(result)
        self.assertEqual(root.tag, 'VXLANInterfaces')
        self.assertEqual(root[0][0].text, 'value1')
        self.assertEqual(root[0][1].text, 'value2')

    def test_format_csv(self):
        data = [{"key1": "value1", "key2": "value2"}]
        result = OutputFormatter.format(data, 'csv')
        self.assertIn('key1,key2', result)
        self.assertIn('value1,value2', result)

    def test_format_script(self):
        data = [{"key1": "value1", "key2": "value2"}]
        result = OutputFormatter.format(data, 'script')
        self.assertIn('key1: value1', result)
        self.assertIn('key2: value2', result)

    def test_format_table(self):
        data = [{"key1": "value1", "key2": "value2"}]
        result = OutputFormatter.format(data, 'table')
        self.assertIn('key1 | key2', result)
        self.assertIn('value1 | value2', result)

    def test_format_invalid_format(self):
        data = [{"key1": "value1", "key2": "value2"}]
        with self.assertRaises(ValueError):
            OutputFormatter.format(data, 'invalid_format')

if __name__ == '__main__':
    unittest.main()
