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

23. **A test burst switched the mail path off.** Fifteen test requests in a few seconds tripped systemd's start limit and latched the intake units off until I reset them. Lesson: a tripped safeguard is a design failure; the service now takes any burst, and the burst is a standing test.

24. **A mute swallowed an approval request.** I muted alerts to restart the monitoring service; a notice that needed a person's yes arrived meanwhile and was only logged. Lesson: notices that need a decision are exempt from a mute or are replayed when it ends.

25. **An analysis command printed private address strings into a cloud assistant session.** I assumed a delimiter in a field and printed the whole field. No titles, order numbers or card data were shown, but the exposure counted. Lesson: run analysis in local programs that print counts only, with no mode that prints a value, and look at a field's shape before parsing it.

26. **Proposed a box-wide tool layer before running the elegance checklist.** Run through the twelve questions it failed on least machinery, one solution per class, a hand-kept list of exposed tools, directness and a second copy of the tool descriptions. Lesson: run the gate before the proposal, not after the question.

27. **Deleted a whole results folder after a test.** I removed everything instead of only the files my tests created. Nothing was lost (the host expires them, the audit trail is elsewhere) but only by luck. Lesson: delete only what you created, by name.

28. **Told the owner a mail was waiting without comparing it with what had been sent.** It was a 98 percent copy of an already-sent letter. Lesson: compare the record before reporting a state.

29. **A retry loop that retried a refused login.** The first version of the mail retry helper retried a wrong-password error three times, because SMTP errors subclass OSError. Lesson: attack a retry helper with the failures you do *not* want retried.

30. **Unreadable data was treated as zero.** A price field that could not be parsed counted as a zero price and would have filed junk under the free-items collection. Lesson: unparseable is its own class, never a default value; found by a hand attack on invented data.
