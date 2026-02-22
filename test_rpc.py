import json, asyncio, time, sys
import aiohttp

TIMEOUT      = 5      # seconds per request
CONCURRENCY  = 100    # parallel requests at once
ETH_PAYLOAD  = json.dumps({
    "jsonrpc": "2.0",
    "method":  "eth_blockNumber",
    "params":  [],
    "id":      1
})

async def ping_rpc(session, url, sem):
    """Return (url, latency_ms) or (url, None) if dead."""
    if not url.startswith("http"):
        return url, None          # skip wss / non-http
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
                if "result" in body or "error" in body:
                    ms = (time.monotonic() - t0) * 1000
                    return url, round(ms, 1)
                return url, None
        except Exception:
            return url, None

async def test_chain(session, chain, sem):
    """Test every rpc in a chain; return chain with only live rpcs sorted by speed."""
    rpcs = chain.get("rpc", [])
    tasks = []
    for entry in rpcs:
        # rpc entries can be plain strings OR objects {"url": ..., ...}
        url = entry if isinstance(entry, str) else entry.get("url", "")
        tasks.append(ping_rpc(session, url, sem))

    results = await asyncio.gather(*tasks)
    latency_map = {url: ms for url, ms in results if ms is not None}

    # Rebuild rpc list: keep only live, sorted fastest first
    live_rpcs = []
    for entry in rpcs:
        url = entry if isinstance(entry, str) else entry.get("url", "")
        if url in latency_map:
            # attach latency metadata if entry is an object
            if isinstance(entry, dict):
                entry = {**entry, "_latencyMs": latency_map[url]}
            live_rpcs.append((latency_map[url], entry))

    live_rpcs.sort(key=lambda x: x[0])
    chain["rpc"] = [e for _, e in live_rpcs]
    return chain, len(live_rpcs)

async def main():
    with open("rpcs.json") as f:
        chains = json.load(f)

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)

    print(f"Testing {len(chains)} chains …", flush=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_chain(session, chain, sem) for chain in chains]
        results = await asyncio.gather(*tasks)

    # Keep chains that still have at least one live RPC
    faster = [chain for chain, live in results if live > 0]
    dead   = [chain for chain, live in results if live == 0]

    print(f"Chains with live RPCs : {len(faster)}")
    print(f"Chains with no live RPCs (dropped): {len(dead)}")

    with open("rpcs-faster.json", "w") as f:
        json.dump(faster, f, separators=(",", ":"))

    print("Saved rpcs-faster.json ✓")

asyncio.run(main())
