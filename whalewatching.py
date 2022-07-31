# vim: ft=python fileencoding=utf-8 sw=4 et sts=4

"""Python script to run our raffle."""

import asyncio
import base64
import collections
import contextlib
import json
import time

import aiohttp

ADDRESS = "stars1u2cup60zf0dujuhd4sth09gvdc383p0jguaqp3"
TEAM_FRAC = 0.384
RAFFLE_FRAC = 1 - TEAM_FRAC

COSMONAUT_MINTER = "stars18tj7yvh7qxv29wtr4angy4gqycrrj9e5j9susaes7vd4tqafzthq5h2m8r"
STARTY_MINTER = "stars1fqsqgjlurc7z2sntulfa0f9alk2ke5npyxrze9deq7lujas7m3ss7vq2fe"
HONOR_STARTY_MINTER = "stars19dzracz083k9plv0gluvnu456frxcrxflaf37ugnj06tdr5xhu5sy3k988"
HU_MINTER = "stars1lnrdwhf4xcx6w6tdpsghgv6uavem353gtgz77sdreyhts883wdjq52aewm"
SK_MINTER = "stars1e3v7h9y3gajtzly37n0g88l9shjlsq2p0pywffty6x676eh6967sg643d2"


async def get_holders(
    minter_addr: str,
    n_tokens: int,
    api_url: str = "https://rest.stargaze-apis.com/cosmwasm/wasm/v1/contract/",
):
    async with aiohttp.ClientSession() as session:
        sg721_url = f"{api_url}/{minter_addr}/smart/eyJjb25maWciOnt9fQ=="
        data = await gather_json(session, sg721_url)
        sg721 = data["data"]["sg721_address"]

        async def get_holder(token_id: int):
            query = (
                base64.encodebytes(
                    f'{{"owner_of":{{"token_id":"{token_id}"}}}}'.encode()
                )
                .decode()
                .strip()
            )
            query_url = f"{api_url}/{sg721}/smart/{query}"
            data = await gather_json(session, query_url)
            try:
                return data["data"]["owner"]
            except KeyError:  # Token not minted yet
                return ""  # Pool wins

        tasks = [get_holder(token_id + 1) for token_id in range(n_tokens)]
        addresses = await asyncio.gather(*tasks)
        return {
            token_id: addr for token_id, addr in enumerate(addresses, start=1) if addr
        }


async def gather_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return await response.json()


def get_boost(
    holder,
    *,
    cosmonaut_counter,
    starty_counter,
    honor_starty_counter,
    hu_counter,
    sk_counter,
):
    """Probability weight boost for each cosmonaut holder."""
    n_startys = starty_counter.get(holder, 0)
    n_honor_startys = honor_starty_counter.get(holder, 0)
    n_planets = hu_counter.get(holder, 0)
    n_baddies = sk_counter.get(holder, 0)
    n_cosmonauts = cosmonaut_counter[holder]
    # Distribute other NFTs equally over all cosmonauts the holder has
    # This may currently give a fraction of an NFT to each cosmonaut, which is not an
    # issue mathematically, but does not make sense from an explorer point of view
    # TODO consider only fixed integer distribution
    starty_boost = min(n_startys / 10 / n_cosmonauts, 1.0)
    honor_starty_boost = min(n_honor_startys / 10 / n_cosmonauts, 1.0)
    planet_boost = min(n_planets / 30 / n_cosmonauts, 1.0)
    sk_boost = min(n_baddies / 10 / n_cosmonauts, 1.0)
    return 1.0 + starty_boost + honor_starty_boost + planet_boost + sk_boost


@contextlib.contextmanager
def print_progress(*args, **kwargs):
    print("\t", *args, "...", **kwargs)
    start = time.time()
    yield
    end = time.time()
    print("\t", "...", f"done ({end - start:.2f} s)\n")


async def main():
    with print_progress("Getting all cosmonaut holders"):
        cosmonauts = await get_holders(COSMONAUT_MINTER, 384)
    cosmonaut_counter = collections.Counter(cosmonauts.values())

    with print_progress("Getting all starty holders"):
        startys = await get_holders(STARTY_MINTER, 1111)
    starty_counter = collections.Counter(startys.values())

    with print_progress("Getting all honor starty holders"):
        honor_startys = await get_holders(HONOR_STARTY_MINTER, 1111)
    honor_starty_counter = collections.Counter(honor_startys.values())

    with print_progress("Getting all HU planet holders"):
        hu_planets = await get_holders(HU_MINTER, 5000)
    hu_counter = collections.Counter(hu_planets.values())

    with print_progress("Getting all SK holders"):
        sk_baddies = await get_holders(SK_MINTER, 2000)
    sk_counter = collections.Counter(sk_baddies.values())

    boosts = [
        get_boost(
            holder,
            cosmonaut_counter=cosmonaut_counter,
            starty_counter=starty_counter,
            honor_starty_counter=honor_starty_counter,
            hu_counter=hu_counter,
            sk_counter=sk_counter,
        )
        for holder in cosmonauts.values()
    ]

    addrs_weight = collections.defaultdict(float)

    for num, addr in cosmonauts.items():
        boost = boosts[num - 1]
        addrs_weight[addr] += boost

    total_weight = sum(elem for elem in addrs_weight.values())
    leaderboard = sorted(addrs_weight.items(), key=lambda e: e[1], reverse=True)

    data = []

    rank = 0
    weight = prev_weight = float("inf")
    for num, (addr, weight) in enumerate(leaderboard, start=1):
        if weight < prev_weight:
            rank = num
            prev_weight = weight
        data.append(
            {
                "Address": addr,
                "Weight": weight,
                "WeightPerc": weight / total_weight * 100,
                "Rank": rank,
            }
        )

    with open("whalewatching.json", "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
