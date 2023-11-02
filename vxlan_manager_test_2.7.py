import unittest
from mock import patch, MagicMock
from vxlan_manager import VXLANManager

class TestVXLANManager(unittest.TestCase):

    def setUp(self):
        self.vxlan_manager_ip = VXLANManager(bridge_tool='ip')
        self.vxlan_manager_brctl = VXLANManager(bridge_tool='brctl')

    def tearDown(self):
        pass

    @patch('subprocess.check_call')
    def test_create_vxlan_interface_ip_success(self, mock_check_call):
        mock_check_call.return_value = 0

        vni = 1001
        src_host = '10.0.0.1'
        dst_host = '10.0.0.2'
        bridge_name = 'br0'

        self.vxlan_manager_ip.create_vxlan_interface(vni, src_host, dst_host, bridge_name)

        calls = [
            patch.call(['ip', 'link', 'add', 'vxlan{vni}'.format(vni=vni), 'type', 'vxlan',
                        'id', str(vni),
                        'local', src_host,
                        'remote', dst_host,
                        'dev', 'eth0',
                        'dstport', str(self.vxlan_manager_ip.default_src_port)]),
            patch.call(['ip', 'link', 'set', 'vxlan{vni}'.format(vni=vni), 'up']),
            patch.call(['ip', 'link', 'set', 'master', bridge_name, 'vxlan{vni}'.format(vni=vni)])
        ]
        mock_check_call.assert_has_calls(calls, any_order=True)

    @patch('subprocess.check_call')
    def test_create_vxlan_interface_ip_failure(self, mock_check_call):
        mock_check_call.side_effect = subprocess.CalledProcessError(1, 'ip')  # Simulate a failure

        vni = 1001
        src_host = '10.0.0.1'
        dst_host = '10.0.0.2'
        bridge_name = 'br0'

        with self.assertRaisesRegexp(SystemExit, '1'):
            self.vxlan_manager_ip.create_vxlan_interface(vni, src_host, dst_host, bridge_name)

    # Update additional test cases similarly for Python 2.7

if __name__ == '__main__':
    unittest.main()
