import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import asyncio
import aiohttp
from tqdm.asyncio import tqdm_asyncio
import time
import random
from asyncio import Lock
import sys

from helpers import write_json_list, parse_match_data

ACCESS_POINT = "https://americas.api.riotgames.com"
API_KEY = "RGAPI-2b53bd4d-1b21-42ad-a494-0a7bc2bf7892"

RATE_LIMIT = 100
WINDOW = 120  # seconds
REQUEST_INTERVAL = WINDOW / RATE_LIMIT  # 1.2s (for 100 requests per 2 minutes)
MAX_CONCURRENT_REQUESTS = 5

concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
last_request_time = 0
request_lock = Lock()

#----------------------------------------------------------------------------------------------------

def parse_match_data(match_data):
    return match_data #TODO

def write_json(json, filename):
    with open(filename, 'w') as f:
        f.write(json)

#---------------------------------------------------------------------------------------------

async def rate_limited_wait():
    global last_request_time
    async with request_lock:
        now = time.monotonic()
        wait_time = last_request_time + REQUEST_INTERVAL - now
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        last_request_time = time.monotonic()

async def limited_get(session, url, max_retries=5):
    async with concurrency_semaphore:
        await rate_limited_wait()
        for attempt in range(max_retries):
            try:
                async with session.get(url) as response:
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 1))
                        print(f"Rate limited, retrying after {retry_after} seconds")
                        await asyncio.sleep(retry_after + random.uniform(0.1, 0.5))
                        continue
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    await asyncio.sleep(2 ** attempt + random.uniform(0.1, 0.5))
                    continue
                raise
        raise Exception(f"Failed after {max_retries} retries: {url}")

#----------------------------------------------------------------------------------------------------
    
async def async_get_league_page(session, tier, division, page, api_key):
    # tier: IRON, BRONZE, SILVER, GOLD, PLATINUM, DIAMOND, MASTER, GRANDMASTER, CHALLENGER
    # division: I, II, III, IV
    na1_access_point = 'https://na1.api.riotgames.com'
    url = f"{na1_access_point}/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}&api_key={api_key}"
    return await limited_get(session, url)

async def async_get_matches(session, puuid, api_key, count = 100):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&api_key={api_key}"
    return await limited_get(session, url)

async def async_get_match_data(session, match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}?api_key={api_key}"
    return await limited_get(session, url)

async def async_get_league_data(tier, division, page, depth, api_key):
    start = time.time()
    print(f"[INFO] Starting async_get_league_data | Tier: {tier}, Division: {division}, Page: {page}, Depth: {depth}")
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        print("[INFO] Fetching league page data...")
        league_data = await async_get_league_page(session, tier, division, page, api_key)
        print(f"[INFO] Retrieved {len(league_data)} players from league page.")

        match_data = []

        async def handle_player(player):
            puuid_short = player['puuid'][:8]
            print(f"[DEBUG] Handling player {puuid_short}...")
            try:
                print(f"[INFO] Fetching match IDs for player {puuid_short}")
                match_ids = await async_get_matches(session, player['puuid'], api_key, count=depth)
                print(f"[INFO] Retrieved {len(match_ids)} matches for {puuid_short}")

                print(f"[INFO] Fetching match data for {puuid_short}...")
                tasks = [async_get_match_data(session, match_id, api_key) for match_id in match_ids]
                results = await asyncio.gather(*tasks)

                print(f"[INFO] Parsing match data for {puuid_short}")
                return [parse_match_data(match) for match in results]

            except Exception as e:
                print(f"[ERROR] Failed to process player {puuid_short}: {e}")
                return []

        print("[INFO] Processing all players asynchronously...")
        tasks = [handle_player(player) for player in league_data]
        results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")

        for result in results:
            match_data.extend(result)

        total_time = time.time() - start_time
        print(f"[INFO] Finished processing all data in {total_time:.2f} seconds. Total matches: {len(match_data)}")
        end = time.time()
        print(f"[INFO] Finished async_get_league_data in {end - start:.2f} seconds")
        return match_data


#----------------------------------------------------------------------------------------------------

async def main(file_path, tier, division, page, depth):
    page_data = await async_get_league_data(tier = tier, 
                                            division = division, 
                                            page = page, 
                                            depth = depth, 
                                            api_key = API_KEY)
    
    write_json_list(page_data, file_path)

if __name__ == "__main__":

    if(len(sys.argv) == 2):
        _, file_path = sys.argv
        print(f"Default case, outputting to: {file_path}")
        asyncio.run(main(file_path, 'DIAMOND', 'I', 1, 5, API_KEY))
        sys.exit(0)

    if len(sys.argv) == 6:
        _, file_path, tier, division, page, depth = sys.argv
        print(f"Running with arguments: {file_path}, {tier}, {division}, {page}, {depth}")
        asyncio.run(main(file_path, tier, division, page, depth))
        sys.exit(0)

    print("Usage: python match_collector.py <file path> <tier> <division> <page> <depth>")
    sys.exit(1)
