# Gen2 activation timeout

Gen2 no longer runs before basic system initialization. A one-shot timer
requests it three minutes after boot, ordered after multi-user.target and
SSH service/socket startup. No boot or SSH unit requires successful Gen2
activation. Failure is recorded in the journal, with no automatic retry.
An active GPU workload still causes the helper to refuse resets.
The installer removes the old sysinit enablement and enables the timer for
the next boot without starting it immediately.

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
