import unittest
from unittest.mock import patch, MagicMock
from vxlan_manager import VXLANManager

class TestVXLANManager(unittest.TestCase):

    def setUp(self):
        self.vxlan_manager_ip = VXLANManager(bridge_tool='ip')
        self.vxlan_manager_brctl = VXLANManager(bridge_tool='brctl')

    def tearDown(self):
        pass

    @patch('subprocess.run')
    def test_create_vxlan_interface_ip_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        vni = 1001
        src_host = '10.0.0.1'
        dst_host = '10.0.0.2'
        bridge_name = 'br0'

        self.vxlan_manager_ip.create_vxlan_interface(vni, src_host, dst_host, bridge_name)

        calls = [
            patch.call(['ip', 'link', 'add', f'vxlan{vni}', 'type', 'vxlan',
                        'id', str(vni),
                        'local', src_host,
                        'remote', dst_host,
                        'dev', 'eth0',
                        'dstport', str(self.vxlan_manager_ip.default_src_port)], check=True),
            patch.call(['ip', 'link', 'set', f'vxlan{vni}', 'up'], check=True),
            patch.call(['ip', 'link', 'set', 'master', bridge_name, f'vxlan{vni}'], check=True)
        ]
        mock_run.assert_has_calls(calls, any_order=True)

    @patch('subprocess.run')
    def test_create_vxlan_interface_ip_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'ip')  # Simulate a failure

        vni = 1001
        src_host = '10.0.0.1'
        dst_host = '10.0.0.2'
        bridge_name = 'br0'

        with self.assertRaises(SystemExit) as cm:
            self.vxlan_manager_ip.create_vxlan_interface(vni, src_host, dst_host, bridge_name)

        self.assertEqual(cm.exception.code, 1)

    @patch('subprocess.run')
    def test_cleanup_vxlan_interface_brctl_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        vni = 1001
        bridge_name = 'br0'

        self.vxlan_manager_brctl.cleanup_vxlan_interface(vni, bridge_name)

        calls = [
            patch.call(['brctl', 'delif', bridge_name, f'vxlan{vni}'], check=True),
            patch.call(['ip', 'link', 'del', f'vxlan{vni}'], check=True)
        ]
        mock_run.assert_has_calls(calls, any_order=True)

    @patch('subprocess.run')
    def test_cleanup_vxlan_interface_brctl_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, 'brctl')  # Simulate a failure

        vni = 1001
        bridge_name = 'br0'

        with self.assertRaises(SystemExit) as cm:
            self.vxlan_manager_brctl.cleanup_vxlan_interface(vni, bridge_name)

        self.assertEqual(cm.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
