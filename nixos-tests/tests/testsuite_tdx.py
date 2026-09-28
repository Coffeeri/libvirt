import os
import textwrap
import time
import unittest
from pathlib import Path

# This import supports both IDE usage from the source tree and execution
# through the Nix test wrapper.
try:
    from ..test_helper.local_machine import LocalMachine  # type: ignore
except Exception:
    from test_helper.local_machine import LocalMachine


def assert_tdx_guest_is_initialized(machine: LocalMachine) -> None:
    """Checks that the guest exposes and initializes TDX."""
    machine.ssh("test -c /dev/tdx_guest")
    machine.ssh("dmesg --color=never | grep -F 'tdx: Guest detected'")


def assert_tdx_guest_generates_quote(machine: LocalMachine) -> None:
    """Checks that the guest can obtain a TD quote from the host QGS.

    Checking the quote is not the hypervisor's job.
    """
    output = machine.ssh(
        textwrap.dedent("""
        set -euo pipefail

        # Ensure configfs is mounted
        if ! mountpoint -q /sys/kernel/config; then
            mount -t configfs none /sys/kernel/config
        fi

        report_dir=/sys/kernel/config/tsm/report
        report="$report_dir/report0"
        quote=/tmp/tdx-quote.bin

        # Create the report directory
        mkdir -p "$report"
        trap 'rmdir "$report"' EXIT

        # Check that the report uses the TDX provider
        test "$(cat "$report/provider")" = tdx_guest

        # Provide 64 bytes of REPORTDATA (nonce)
        head -c 64 /dev/urandom > "$report/inblob"

        # Retrieve the quote
        cat "$report/outblob" > "$quote"

        # Check if the quote is empty
        size=$(wc -c < "$quote")
        if [ "$size" -eq 0 ]; then
            echo "the guest returned an empty TD quote. Is the Intel Quote Generation Service running on the host and listening on /var/run/tdx-qgs/qgs.socket?" >&2
            exit 1
        fi

        # Show the quote
        echo "TD quote size: $size bytes"
        hexdump -C "$quote"
        """).strip()
    )
    print(output)


class TdxTests(unittest.TestCase):
    """Exercises confidential computing in an Intel TDX guest directly with Cloud Hypervisor, without libvirt."""

    def setUp(self) -> None:
        print(f"\n\nRunning test: {self._testMethodName}\n\n")
        self.test_start_time = time.time()
        # Keep this address and MAC in sync with the dnsmasq reservation in
        # hardware/modules/host-services.nix from the hardware repository.
        # The reservation maps be:e3:00:00:00:01 to 192.168.100.70.
        self.machine = LocalMachine(
            guest_ip="192.168.100.70",
            guest_mac="be:e3:00:00:00:01",
            tap_device="tap15",
            platform="tdx",
            cloud_hypervisor=Path(os.environ["TDX_CLOUD_HYPERVISOR"]),
            firmware=Path(os.environ["TDX_FIRMWARE"]),
            guest_image=Path(os.environ["TDX_IMAGE"]),
            image_type=os.environ.get("TDX_IMAGE_TYPE", "raw"),
        )
        self.addCleanup(self.machine.cleanup)
        self.addCleanup(self._save_logs)
        self.machine.start()
        self.machine.wait_for_ssh()

    def tearDown(self) -> None:
        duration_s = int(time.time() - self.test_start_time)
        print(f"\n\nRan test {self._testMethodName} in {duration_s}s\n\n")

    def _save_logs(self) -> None:
        log_dir = os.environ.get("DBG_LOG_DIR")
        if log_dir:
            self.machine.save_logs(Path(log_dir) / self._testMethodName / "tdx")

    def test_tdx_guest_generates_quote(self) -> None:
        """Verifies that the guest can obtain a TD quote from the host QGS."""
        assert_tdx_guest_generates_quote(self.machine)

    def test_tdx_guest_is_initialized(self) -> None:
        """Verifies that the TDX guest is initialized."""
        assert_tdx_guest_is_initialized(self.machine)

    def test_tdx_guest_shuts_down(self) -> None:
        """Verifies that the TDX guest can shut down cleanly."""
        self.machine.shutdown()
        self.assertFalse(self.machine.is_running())

    def test_tdx_guest_survives_reboot(self) -> None:
        """Verifies that TDX remains active after a guest reboot."""
        self.machine.reboot()
        assert_tdx_guest_is_initialized(self.machine)


def suite() -> unittest.TestSuite:
    testcases = [
        TdxTests.test_tdx_guest_generates_quote,
        TdxTests.test_tdx_guest_is_initialized,
        TdxTests.test_tdx_guest_shuts_down,
        TdxTests.test_tdx_guest_survives_reboot,
    ]

    test_suite = unittest.TestSuite()
    for testcase_method in testcases:
        test_suite.addTest(TdxTests(testcase_method.__name__))
    return test_suite


runner = unittest.TextTestRunner()
if not runner.run(suite()).wasSuccessful():
    raise Exception("Test run unsuccessful")
