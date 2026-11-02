# Gen2 activation timeout

The boot oneshot has a 120-second start timeout and a 10-second stop
timeout. systemd terminates its control group, including child commands,
and does not automatically retry. A userspace driver command that hangs
must not leave Gen2 activation waiting indefinitely.

Install the updated unit with `sudo ./install-service.sh auto`. This changes
future service starts; it does not repair a machine already stuck at boot.
For a one-time recovery, append
`systemd.mask=cmp170-gen2-second-pass.service` to the Linux command line in GRUB.

This is not a guarantee of recovery from a kernel/PCIe lockup: tasks stuck
in uninterruptible kernel sleep may not respond even to SIGKILL. Diagnose
the driver and retain a known-working kernel/module backup in that case.
