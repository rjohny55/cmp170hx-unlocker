"""Safety checks for the explicitly opt-in, audited G292 host example."""
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BAR1HostExampleTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(['bash', '-n', str(ROOT / 'tools/activate-bar1-host194.sh')], check=True)

    def test_is_not_an_early_boot_dependency_or_restart_loop(self):
        service = (ROOT / 'tools/cmp170-bar1-p2p-host194.service').read_text()
        timer = (ROOT / 'tools/cmp170-bar1-p2p-host194.timer').read_text()
        self.assertIn('After=multi-user.target ssh.service ssh.socket', service)
        self.assertIn('TimeoutStartSec=300s', service)
        self.assertIn('TimeoutStopSec=10s', service)
        self.assertIn('Restart=no', service)
        self.assertNotIn('Before=', service)
        self.assertNotIn('WantedBy=', service)
        self.assertIn('OnBootSec=3min', timer)

    def test_network_scope_idle_and_boot_baseline_guards(self):
        script = (ROOT / 'tools/activate-bar1-host194.sh').read_text()
        self.assertIn('$(hostname) == gigabyte', script)
        self.assertIn('Mixed NVIDIA GPU host; refusing', script)
        self.assertIn('for iface in /sys/class/net/*', script)
        self.assertIn('Refusing non-GPU branch device', script)
        self.assertIn('Active CUDA clients; leaving driver unchanged', script)
        self.assertNotIn('/sys/bus/pci/rescan', script)
        self.assertNotIn('BRIDGE_CONTROL', script)
        self.assertNotIn('update-initramfs', script)
        self.assertNotIn('depmod', script)
        self.assertIn('autoload_block_owned=1', script)
        self.assertIn('56/56 directed pairs passed real peer reads and writes.', script)

    def test_udev_builtin_and_modprobe_are_both_blocked_during_rescan(self):
        config = (ROOT / 'tools/cmp170-bar1-maintenance.conf').read_text()
        self.assertIn('install nvidia /bin/false', config)
        for name in ('nvidia', 'nvidia_drm', 'nvidia_modeset', 'nvidia_uvm', 'nvidia_peermem'):
            self.assertIn('blacklist ' + name + '\n', config)
        script = (ROOT / 'tools/activate-bar1-host194.sh').read_text()
        self.assertIn('udevadm control --reload', script)
        self.assertIn('udevadm settle --timeout=12', script)
