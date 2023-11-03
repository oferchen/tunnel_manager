import unittest
from unittest.mock import MagicMock, mock_open, patch

from tunnel_manager import TunnelManager, TunnelManagerError


class TestTunnelManager(unittest.TestCase):
    def setUp(self):
        self.vxlan_manager = TunnelManager("vxlan")
        self.geneve_manager = TunnelManager("geneve")

    @patch("tunnel_manager.subprocess.run")
    def test_create_vxlan_interface_success(self, mock_run):
        self.vxlan_manager.create_tunnel_interface(1001, "192.168.1.1", "192.168.1.2", "br0")
        mock_run.assert_called()

    @patch("tunnel_manager.subprocess.run")
    def test_create_vxlan_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ip")
        with self.assertRaises(TunnelManagerError):
            self.vxlan_manager.create_tunnel_interface(1001, "192.168.1.1", "192.168.1.2", "br0")

    @patch("tunnel_manager.subprocess.run")
    def test_cleanup_vxlan_interface_success(self, mock_run):
        self.vxlan_manager.cleanup_tunnel_interface(1001, "br0")
        mock_run.assert_called()

    @patch("tunnel_manager.subprocess.run")
    def test_cleanup_vxlan_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ip")
        with self.assertRaises(TunnelManagerError):
            self.vxlan_manager.cleanup_tunnel_interface(1001, "br0")

    @patch("tunnel_manager.socket.socket")
    def test_validate_vxlan_connectivity_success(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        self.vxlan_manager.validate_connectivity("192.168.1.1", "192.168.1.2", 1001)
        mock_socket_instance.connect.assert_called_with(("192.168.1.2", 4789))

    @patch("tunnel_manager.socket.socket")
    def test_validate_vxlan_connectivity_failure(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        mock_socket_instance.connect.side_effect = socket.error
        with self.assertRaises(TunnelManagerError):
            self.vxlan_manager.validate_connectivity("192.168.1.1", "192.168.1.2", 1001)

    @patch("tunnel_manager.subprocess.run")
    def test_create_geneve_interface_success(self, mock_run):
        self.geneve_manager.create_tunnel_interface(1001, "192.168.1.1", "192.168.1.2", "br0")
        mock_run.assert_called()

    @patch("tunnel_manager.subprocess.run")
    def test_create_geneve_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ip")
        with self.assertRaises(TunnelManagerError):
            self.geneve_manager.create_tunnel_interface(1001, "192.168.1.1", "192.168.1.2", "br0")

    @patch("tunnel_manager.subprocess.run")
    def test_cleanup_geneve_interface_success(self, mock_run):
        self.geneve_manager.cleanup_tunnel_interface(1001, "br0")
        mock_run.assert_called()

    @patch("tunnel_manager.subprocess.run")
    def test_cleanup_geneve_interface_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ip")
        with self.assertRaises(TunnelManagerError):
            self.geneve_manager.cleanup_tunnel_interface(1001, "br0")

    @patch("tunnel_manager.socket.socket")
    def test_validate_geneve_connectivity_success(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        self.geneve_manager.validate_connectivity("192.168.1.1", "192.168.1.2", 1001)
        mock_socket_instance.connect.assert_called_with(("192.168.1.2", 6081))

    @patch("tunnel_manager.socket.socket")
    def test_validate_geneve_connectivity_failure(self, mock_socket):
        mock_socket_instance = mock_socket.return_value.__enter__.return_value
        mock_socket_instance.connect.side_effect = socket.error
        with self.assertRaises(TunnelManagerError):
            self.geneve_manager.validate_connectivity("192.168.1.1", "192.168.1.2", 1001)


if __name__ == "__main__":
    unittest.main()
