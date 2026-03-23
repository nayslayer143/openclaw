# Jordan's Task List — OpenClaw Setup
> Last updated: 2026-03-20
> Priority order. Each item has what YOU need to do — Clawmpson handles everything else once you hand it off.
> Estimated time per item in [brackets].

---

## 🔴 PRIORITY 1 — Unlocks Revenue (Do These First)

### 1. Stripe API Key [5 min]
**Why first:** Clawmpson can't invoice or collect money without it.
1. Go to dashboard.stripe.com → Developers → API Keys
2. Copy the Secret Key (starts with `sk_live_...`)
3. Run: `bash ~/openclaw/scripts/keys.sh --set stripe sk_live_YOUR_KEY`
4. Also get test key: `sk_test_...` → `bash ~/openclaw/scripts/keys.sh --set stripe-test sk_test_YOUR_KEY`
> Clawmpson will: wire invoicing, set up meOS + xyz.cards payment links, configure webhook alerts

---

### 2. Upwork Account for Clawmpson [15 min]
**Why:** Highest-paying gig platform. Most AI automation demand.
1. Go to upwork.com → Create account
2. Name: **Clawmpson AI** (or your preferred operating name)
3. Category: Web Development + AI/ML + Writing
4. Add a profile photo (generate one or use a pro headshot)
5. Save login in: `bash ~/openclaw/scripts/keys.sh --set upwork-email YOUR@EMAIL`
6. Save password in macOS Keychain manually (Keychain Access app → New Password Item → `upwork.com`)
> Clawmpson will: complete the profile bio, set hourly rates, start scanning + bidding

---

### 3. Fiverr Account for Clawmpson [10 min]
**Why:** Volume gig platform. Good for recurring small orders.
1. Go to fiverr.com → Join as Seller
2. Username suggestion: `clawmpsonai` or `omegamegacorp`
3. Save login same as above
> Clawmpson will: create 5 gig listings (AI automation, Python scripts, landing pages, content writing, Telegram bots)

---

### 4. Google Calendar API Access [15 min]
**Why:** Clawmpson needs to know your schedule to suppress pings during Z-time and plan work cycles.
1. Go to console.cloud.google.com
2. Create project: "OpenClaw"
3. Enable: Google Calendar API
4. Create credentials: OAuth 2.0 Client ID (Desktop app type)
5. Download the JSON file → save to `~/openclaw/.google-credentials.json`
> Clawmpson will: build the sync script, wire Z-schedule detection into all crons

---

## 🟠 PRIORITY 2 — Clawmpson Gets His Own Identity

### 5. Clawmpson's Email Address [10 min]
**Options (pick one):**
- **Easiest:** Create `clawmpson@gmail.com` or `clawmpsonai@gmail.com`
- **Pro:** Add `clawmpson@omegamegacorp.com` via Google Workspace ($6/mo)
1. Create the account
2. Save: `bash ~/openclaw/scripts/keys.sh --set clawmpson-email THEADDRESS@gmail.com`
3. Enable IMAP: Gmail Settings → See All Settings → Forwarding and POP/IMAP → Enable IMAP
4. Generate App Password: Google Account → Security → 2FA → App Passwords
5. Save app password: `bash ~/openclaw/scripts/keys.sh --set gmail-app-password YOUR_APP_PASSWORD`
> Clawmpson will: monitor inbox, send proposals + invoices, receive client replies

---

### 6. Twitter/X Account for Clawmpson [10 min]
**Why:** Build audience, post about builds, attract inbound gig leads.
1. Go to x.com → Create account
2. Username: `@clawmpsonai` or `@clawmpson_dev`
3. Bio suggestion: "AI agent building products + shipping gigs | Powered by @omegamegacorp"
4. Save login → pass to Clawmpson
> Clawmpson will: post daily build updates, engage with AI/dev community, attract leads

---

### 7. LinkedIn Profile for Clawmpson [15 min]
**Why:** B2B leads + higher-paying freelance clients.
1. Create profile (use Clawmpson AI as name or a persona name)
2. Headline: "AI Automation Specialist | Python • iOS • Claude API • Stripe"
3. Save login
> Clawmpson will: write full profile, connect with target clients, post case studies

---

### 8. Malt.com Profile [10 min]
**Why:** European freelance marketplace, less saturated than Upwork for AI work.
1. Go to malt.com → Sign up as Freelancer
2. Category: Software Development / AI
3. Save login
> Clawmpson will: complete profile, set rates, scan for projects

---

## 🟡 PRIORITY 3 — Supercharging Clawmpson's Search

### 9. Serper.dev API Key [5 min — FREE tier available]
**Why:** Real Google search results via API. Unlocks actual live gig scanning, lead gen, competitor research.
1. Go to serper.dev → Sign up (free tier: 2,500 queries/mo)
2. Copy API key
3. Run: `bash ~/openclaw/scripts/keys.sh --set serper YOUR_KEY`
> Clawmpson will: wire into gig scanner for real-time searches, replace simulated research

---

### 10. Jina AI Reader API [5 min — FREE]
**Why:** Reads any webpage cleanly for Clawmpson to analyze. No scraping friction.
1. Go to jina.ai → Get API Key (free tier: generous)
2. Run: `bash ~/openclaw/scripts/keys.sh --set jina YOUR_KEY`
> Clawmpson will: read job posts, competitor sites, client landing pages for proposal research

---

## 🟢 PRIORITY 4 — Bigger Plays (When Ready)

### 11. Crypto Wallet Seed Funds
- Decide: how much to seed Clawmpson's operations wallet? (recommend: $50-200 USDC to start)
- Clawmpson will generate the wallet address — you just send funds when ready

### 12. Freelancer.com Account [10 min]
- Similar to Upwork but more price-competitive. Good for volume.
- Create at freelancer.com → Developer profile

### 13. PeoplePerHour Account [10 min]
- UK-based but global. Good for European clients.
- Create at peopleperhour.com

### 14. Contra Account [5 min]
- Modern async freelance. Good for product builders.
- Create at contra.com

---

## ✅ Already Done by Clawmpson
- [x] Anthropic key stored (Keychain + .env)
- [x] OpenAI key in .env
- [x] meOS iOS app built + running on simulator
- [x] All crons live: health, intel, morning brief, idea engine, bounty scan, gig scanner (3x/day), skill upgrade (Mondays)
- [x] MiroFish validated (4.27/5)
- [x] AutoResearch running: agentic income, arbitrage, ClawMart skills, freelance landscape, web search tools

---

## 📬 Clawmpson Pings You When:
- Hot gig found (>7/10 confidence) → reply with number to approve bid
- Proposal ready to send → your review + 1-click approve
- Payment received → celebratory ping
- Ideas brief ready (every morning) → reply to approve research
- Approval needed before spending money or deploying to prod

---
*This file is updated by Clawmpson after each completed setup item.*
*Estimated total time to complete Priority 1-2: ~75 minutes*
