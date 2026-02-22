import json, asyncio, time
import aiohttp

# ── Config ──────────────────────────────────────────────────────────
TIMEOUT     = 5      # seconds to wait per endpoint
CONCURRENCY = 150    # max parallel requests

ETH_PAYLOAD = json.dumps({
    "jsonrpc": "2.0",
    "method":  "eth_blockNumber",
    "params":  [],
    "id":      1
}).encode()

# ── Ping a single URL ────────────────────────────────────────────────
async def ping(session, url: str, sem: asyncio.Semaphore):
    """
    Returns latency in ms if alive, or None if dead / non-HTTP.
    Skips wss:// and any non-http scheme.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        return None
    async with sem:
        try:
            t0 = time.monotonic()
            async with session.post(
                url,
                data=ETH_PAYLOAD,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            ) as resp:
                body = await resp.json(content_type=None)
                # Valid JSON-RPC response must have "result" or "error"
                if "result" in body or "error" in body:
                    return round((time.monotonic() - t0) * 1000, 1)
                return None
        except Exception:
            return None

# ── Test one chain ───────────────────────────────────────────────────
async def test_chain(session, chain: dict, sem: asyncio.Semaphore):
    """
    Pings every rpc entry.
    Input  entry shape : { "url": "https://...", ...otherFields }
    Output entry shape : { "url": "https://...", ...otherFields }  ← identical, no extra keys
    Dead endpoints are dropped; live ones sorted fastest → slowest.
    """
    rpc_entries = chain.get("rpc", [])

    # Normalise every entry to (url_string, original_entry_as_dict)
    normalised = []
    for entry in rpc_entries:
        if isinstance(entry, dict):
            normalised.append((entry.get("url", ""), entry))
        elif isinstance(entry, str):
            # Wrap bare string → object to match target structure
            normalised.append((entry, {"url": entry}))
        else:
            normalised.append(("", {}))

    # Ping all URLs concurrently
    latencies = await asyncio.gather(
        *[ping(session, url, sem) for url, _ in normalised]
    )

    # Keep only live entries, sorted by latency
    live = sorted(
        [
            (ms, dict(entry_obj))          # copy so we don't mutate original
            for (_, entry_obj), ms in zip(normalised, latencies)
            if ms is not None
        ],
        key=lambda x: x[0]                 # sort fastest first
    )

    chain_out = dict(chain)                 # shallow copy — preserves all top-level fields
    chain_out["rpc"] = [obj for _, obj in live]   # clean entries, no latency key injected

    return chain_out, len(live)

# ── Main ─────────────────────────────────────────────────────────────
async def main():
    with open("rpcs.json", encoding="utf-8") as f:
        chains = json.load(f)

    print(f"Loaded {len(chains)} chains from rpcs.json", flush=True)

    sem       = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        results = await asyncio.gather(
            *[test_chain(session, chain, sem) for chain in chains]
        )

    alive, dead = [], []
    for chain, live_count in results:
        (alive if live_count > 0 else dead).append(chain)

    print(f"\n✅  Chains with live RPCs       : {len(alive)}")
    print(f"❌  Chains fully dead (dropped) : {len(dead)}")
    if dead:
        names = [c.get("name", "?") for c in dead]
        print("    Dropped:", ", ".join(names[:10]),
              ("…" if len(names) > 10 else ""))

    # Output structure identical to rpcs.json
    with open("rpcs-faster.json", "w", encoding="utf-8") as f:
        json.dump(alive, f, ensure_ascii=False, separators=(",", ":"))

    print("\n💾  Saved rpcs-faster.json ✓")

asyncio.run(main())
