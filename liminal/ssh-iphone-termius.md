# SSH iPhone Access via Tailscale + Termius

**Status:** Parked — Termius setup didn't complete
**Blocked on:** Remote Login (SSH) needs to be enabled on Mac, then Termius configured

---

## What's already done

- Tailscale installed and authenticated (`jordan@`, IP: `100.79.255.73`)
- tmux config written to `~/.tmux.conf` (Ctrl+a prefix, mouse on, mobile-friendly)
- `~/openclaw/scripts/claude-session.sh` — run this after SSH to get persistent Claude session
- Shell alias `claw` added to `~/.zshrc`

## What's left

1. **Enable SSH on Mac:**
   System Settings → General → Sharing → Remote Login → ON → All users

2. **Install on iPhone:**
   - Tailscale (App Store) — log in as jordan@
   - Termius (App Store) — free SSH client

3. **Add host in Termius:**
   - Host: `100.79.255.73`
   - Username: `nayslayer`
   - Auth: Mac login password (or add SSH key for passwordless)
   - Port: 22

4. **Test connection**, then run `claw` to attach Claude Code session

5. **After SSH works:** build GonzoClaw chat UI (part b) — web-based Claude chat at www.asdfghjk.lol/chat

## Notes
- Tailscale handles the network — works from any network, no port forwarding needed
- tmux keeps Claude session alive if phone disconnects — just reconnect and run `claw`
- Cloudflare SSH tunnel was considered but requires `cloudflared` on client — not Termius-compatible
