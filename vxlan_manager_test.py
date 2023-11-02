import unittest
from unittest.mock import patch, Mock
from vxlan_manager import VXLANManager, create_vxlan_tunnel, cleanup_vxlan_tunnel

class TestVXLANManager(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    @patch('subprocess.call')
    @patch('subprocess.Popen')
    def test_create_vxlan_interface(self, mock_call, mock_popen):
        mock_call.side_effect = [0, 0, 0]  # Simulate successful subprocess calls
        mock_popen.return_value = Mock()  # Mock the subprocess.Popen object

        vni = 1001
        src_host = '10.0.0.1'
        dst_host = '10.0.0.2'
        bridge_name = 'br0'
        src_port = 4789
        dst_port = 4789

        vxlan_manager = VXLANManager()
        vxlan_manager.create_vxlan_interface(vni, src_host, dst_host, bridge_name, src_port, dst_port)

        mock_call.assert_called_with(['ip', 'link', 'add', f'vxlan{vni}', 'type', 'vxlan',
                                     'id', str(vni),
                                     'local', src_host,
                                     'remote', dst_host,
                                     'dev', 'eth0',
                                     'dstport', str(src_port)])
        mock_call.assert_called_with(['ip', 'link', 'set', f'vxlan{vni}', 'up'])
        mock_call.assert_called_with(['brctl', 'addif', bridge_name, f'vxlan{vni}'])

    # Write similar test cases for other methods
    
if __name__ == '__main__':
    unittest.main()
