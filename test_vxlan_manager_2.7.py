import socket
import unittest

import mock

from vxlan_manager import VXLANManager, VXLANManagerError


class TestVXLANManager(unittest.TestCase):
    def setUp(self):
        self.vxlan_manager = VXLANManager()
        self.vni = 1001
        self.src_host = '192.168.1.1'
        self.dst_host = '192.168.1.2'
        self.bridge_name = 'br0'
        self.src_port = 1234
        self.dst_port = 5678
        self.dev = 'eth0'

    @mock.patch('subprocess.check_call')
    def test_create_vxlan_interface(self, mock_check_call):
        self.vxlan_manager.create_vxlan_interface(self.vni, self.src_host, self.dst_host, self.bridge_name, self.src_port, self.dst_port, self.dev)
        mock_check_call.assert_has_calls([
            mock.call(['ip', 'link', 'add', 'vxlan{0}'.format(self.vni), 'type', 'vxlan', 'id', str(self.vni),
                       'local', self.src_host, 'remote', self.dst_host, 'dev', self.dev, 'dstport', str(self.dst_port)]),
            mock.call(['ip', 'link', 'set', 'vxlan{0}'.format(self.vni), 'up']),
            mock.call(['ip', 'link', 'set', 'master', self.bridge_name, 'vxlan{0}'.format(self.vni)])
        ])

    @mock.patch('subprocess.check_call')
    def test_cleanup_vxlan_interface(self, mock_check_call):
        self.vxlan_manager.cleanup_vxlan_interface(self.vni, self.bridge_name)
        mock_check_call.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'vxlan{0}'.format(self.vni), 'nomaster']),
            mock.call(['ip', 'link', 'del', 'vxlan{0}'.format(self.vni)])
        ])

    @mock.patch('socket.socket')
    def test_validate_connectivity_success(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        mock_socket_instance.connect.return_value = None
        self.vxlan_manager.validate_connectivity(self.src_host, self.dst_host, self.vni, self.dst_port)
        mock_socket_instance.connect.assert_called_once_with((self.dst_host, self.dst_port))

    @mock.patch('socket.socket')
    def test_validate_connectivity_failure(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        mock_socket_instance.connect.side_effect = socket.error
        with self.assertRaises(VXLANManagerError):
            self.vxlan_manager.validate_connectivity(self.src_host, self.dst_host, self.vni, self.dst_port)
        mock_socket_instance.connect.assert_called_once_with((self.dst_host, self.dst_port))

    @mock.patch('subprocess.check_output')
    def test_list_vxlan_interfaces(self, mock_check_output):
        mock_check_output.return_value = 'vxlan{0}:'.format(self.vni)
        output = self.vxlan_manager.list_vxlan_interfaces(['vni'], 'script')
        self.assertIn('vxlan{0}'.format(self.vni), output)

if __name__ == '__main__':
    unittest.main()
