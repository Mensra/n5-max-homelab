# Mistakes I made (so you don't have to)

This build was done with an AI assistant doing most of the hands-on work under my direction. Between us
we made real mistakes, and some of them took services down. They're listed here because the fixes are
the most useful part.

## Things that broke something

1. **A documentation command executed a live rollback.** A block of notes was written to a file with an
   unquoted shell heredoc as root. The notes contained a command in backticks -- and the shell ran it: a
   `zfs rollback` of the live AI container. That hung the journal service, the reboot hung behind it,
   and the box needed a forced power-off.
   **Lesson:** quote heredocs (`<<'EOF'`) or write files with an editor, never unquoted as root.

2. **A ZFS rollback followed by an immediate restart corrupted Docker's metadata.** OpenZFS 2.4 can
   serve stale page-cache data right after a rollback (openzfs issue #10931). Restarting the container
   straight away read old cached blocks.
   **Lesson:** after any rollback, `sync; echo 1 > /proc/sys/vm/drop_caches` before starting anything.

3. **Rebooting with a process stuck in "D" state hung the reboot.** Use the SysRq sync/unmount/reboot
   sequence instead of waiting.

4. **Container limits plus the GPU memory ceiling added up to more than the machine had.** A 75 GB
   container limit plus a 56 GB GTT ceiling on a 128 GB box: a big image-model load took the whole host
   down, not just its own container.

5. **A home-made watchdog keyed on load average killed healthy services in a loop.** Load average counts
   normal start-up churn. Replaced with `systemd-oomd` (memory-pressure based).

6. **OS updates applied without reading the release notes broke Docker networking.** Ubuntu's stock
   `nftables` service flushed Docker's firewall rules when its package updated. The same update on the
   DNS container would have taken the house offline; it was stopped in time.

7. **A sync script flooded Proxmox's task log and silently stopped the nightly backups for days.**

## Things that were wrong without anyone noticing

8. **Hardware transcoding was "set up" but never switched on.** `/dev/dri` was passed through; Jellyfin was
   still set to "none" and transcoding on the CPU for two weeks.

9. **Documented emergency passwords didn't work.** Both Samba passwords in the credentials file were stale.
   Found only by stopping the SSO server and actually trying every fallback login.

10. **The restore guide pointed at the wrong place.** One restore step extracted into an empty, retired
    folder (it would have "succeeded" and restored nothing); another told you to `chown` restored app data,
    which would have broken apps whose folders legitimately mix owners.

11. **My own monitoring kept the backup drive from ever sleeping.** A per-minute temperature logger polled
    the USB backup enclosure -- undoing an earlier fix that had made it sleep. Its fan was fine; it just
    never got a rest.

12. **I trusted a product page over the hardware.** The spec sheet said no internal PCIe slot; `dmidecode`
    showed one (already occupied by the Thunderbolt card). Check the machine itself.

13. **Fan theory was wrong twice** before BIOS screenshots and controlled tests settled it: the HDD fans
    follow ambient temperature, not the drives.

## Process mistakes

14. **Secrets printed while checking them.** A few times a password or token went to the screen while
    verifying it. Check secrets by comparing, never by displaying -- and rotate anything that was shown.

15. **"Done" claimed before checking the live system.** Tracking notes go stale; verify the real state
    before marking anything finished or asking someone else to act on it.

16. **The same password written in several places.** Every copy is a chance to go stale. One place, and
    readable placeholders (`{{PW_NAME}}`) everywhere else.

## Added October 2026

17. **A "list every getter" sweep crashed two radios.** To compare the settings of two identical Wi-Fi units
    the assistant ran all ~1,800 driver commands without arguments on both production radios at once, using a
    deny-list of "dangerous" words. One command crashed the 5 GHz firmware on both units; both rebooted and
    about fifteen devices lost Wi-Fi for two minutes.
    **Lesson:** allow-list known read-only commands, compare configuration from the exported settings (text)
    instead of the live driver, and try anything untested on one unit first.

18. **A critical alert was routed through the thing it reports on.** The first design sent Proxmox backup
    failures through Home Assistant, which runs on that Proxmox host: when the host is the problem, the alert
    dies with it. The owner caught it.
    **Lesson:** a critical function alerts through the shortest path with no shared dependency.

19. **A log line claimed a check was running that had never been installed.** The change had been written to a
    scratch copy; later edits started from the installed file, so it was silently dropped. Found by reading
    the check's state file.
    **Lesson:** log a change only after reading the live result of that change; the log tool now stamps the
    real time and takes the text after the result has been read.

20. **Hand-typed timestamps in the build log** were invented, some in the future.
    **Lesson:** the time comes from the clock, never from the writer.

21. **"HTTP 200" was treated as "delivered".** The webhook answers 200 to any id. Delivery is proven by the
    receiving side acting on it, so the id now lives in one place only.

22. **A "simplification" removed a deliberate copy.** Collapsing three backup scripts' identical retention
    numbers into one server-side table would also have changed container-backup retention, and removed the
    independence that makes each script self-contained. Deliberate duplication on a critical path is
    denormalization: keep it, list it, and add a check that the copies stay equal.
