# Strategy -- Future Features

## Phase 2: Visual Intelligence Layer
- **Vision model analysis** -- Feed top-engagement post images to a vision model (GPT-4V, Claude) to detect chart screenshots, portfolio screenshots, and meme templates. Visual content often precedes text-based signals.
- **Reels script generator** -- Analyze top-performing finance Reels to extract script templates (hook, content, CTA patterns). Generate new Reels scripts that match proven engagement patterns.
- **Image-to-ticker extraction** -- Use OCR on chart screenshots to detect ticker symbols, price levels, and timeframes that aren't mentioned in captions.

## Phase 3: Influencer Intelligence
- **Influencer accuracy scoring** -- Track which finfluencers have high hit rates on their bullish/bearish calls. Weight their signals higher over time.
- **Follower-weighted sentiment** -- Accounts with larger followings get higher signal weight. A 500k-follower finfluencer calling bullish matters more than a 100-follower account.
- **Influencer partnership discovery** -- Identify rising finfluencers (high engagement rate, growing followers) who align with specific tickers or narratives. Potential partnership or collaboration targets.
- **Content calendar analysis** -- Track posting frequency and timing patterns of top finfluencers to predict when major calls will be made.

## Phase 4: Hashtag Velocity & Trend Detection
- **Hashtag velocity anomaly detection** -- Track posts-per-hour per hashtag. 10x spike from baseline = retail FOMO event, generate high-urgency alert.
- **Emerging hashtag discovery** -- Monitor co-occurring hashtags. If #bitcoin posts suddenly include #bullrun or #altseason, that's a signal shift.
- **Cross-platform hashtag correlation** -- Compare Instagram hashtag velocity with Twitter/X trending topics and Reddit post volume. Agreement = stronger signal.

## Phase 5: Content Strategy Automation
- **Auto-generate Instagram content** -- Use crawled top-performing posts as style references to generate carousel posts, infographics, and caption templates.
- **Engagement prediction model** -- Train a simple model on scraped engagement data to predict which content formats and topics will perform best.
- **Optimal posting time analysis** -- Analyze timestamp data to determine when finance content gets the most engagement on Instagram.

## Phase 6: Cross-Platform Correlation
- **Instagram-Reddit divergence** -- Compare Instagram sentiment (#crypto) with Reddit sentiment (r/cryptocurrency). Divergence = potential opportunity signal.
- **Instagram-price divergence** -- Mostly bullish Instagram captions but price falling = potential retail trap. Requires price feed integration.
- **Story/Reels engagement vs. feed** -- Track which content format (Stories, Reels, feed posts) drives the most engagement for finance content. Shifts may indicate platform algorithm changes.

## Phase 7: Real-time & API
- **Graph API full integration** -- When token available, use webhooks for real-time hashtag monitoring instead of polling.
- **Ollama analysis** -- Feed top-engagement captions to local LLM for structured thesis extraction and narrative classification.
- **Narrative clustering** -- Group signals by emerging narrative themes rather than just individual hashtags or tickers.
