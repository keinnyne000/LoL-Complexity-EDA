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
API_KEY = "RGAPI-a264d8c4-2502-4f2a-a234-95e58fe8b903"

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
    if(tier == 'MASTER' or tier == 'GRANDMASTER' or tier == 'CHALLENGER'):
        url = f"{na1_access_point}/lol/league/v4/{tier.lower()}leagues/by-queue/RANKED_SOLO_5x5?api_key={api_key}"
        response = await limited_get(session, url)
        return response['entries']
    else:
        url = f"{na1_access_point}/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}&api_key={api_key}"
        return await limited_get(session, url)

async def async_get_matches(session, puuid, api_key, count = 100):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&api_key={api_key}"
    return await limited_get(session, url)

async def async_get_match_data(session, match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}?api_key={api_key}"
    return await limited_get(session, url)

async def handle_player(session, player, api_key, depth):
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

async def get_division_matches(tier, division, player_count, depth, api_key):
    start = time.time()
    print(f"[INFO] Starting async_get_league_data | Tier: {tier}, Division: {division}, Player count: {player_count}, Depth: {depth}")
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        print("[INFO] Fetching league page data...")
        results = []
        page_number = 1
        while(len(results) < player_count):
            print(f"[INFO] Fetching league page data no.{len(results)}...")
            page_data = await async_get_league_page(session, tier, division, page_number, api_key)
            results.extend(page_data)
            page_number += 1
        players = results[:player_count]
        print(f"[INFO] Retrieved {len(players)} players from league page.")

        print("[INFO] Processing all players asynchronously...")
        tasks = [handle_player(session, player, api_key, depth) for player in players]
        results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")

        match_data = []
        for result in results:
            match_data.extend(result)

        total_time = time.time() - start_time
        print(f"[INFO] Finished processing all data in {total_time:.2f} seconds. Total matches: {len(match_data)}")
        
        return match_data


#----------------------------------------------------------------------------------------------------

async def get_distribution_matches(player_count: int, depth: int, distribution, api_key):
    start = time.time()
    print(f"[INFO] Starting async_sample_distribution | Player Count: {player_count}, Depth: {depth}")
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        players = []
        for d in distribution.iloc():
            count = int(np.ceil(d['percentage'] * player_count))
            results = []
            print(f"[INFO] Sampling {count} players from {d['tier']} {d['division']}...")
            page_number = 1
            while(len(results) < count):
                print(f"[INFO] Fetching league page data no.{len(results)} for {d['tier']} {d['division']}...")
                page_data = await async_get_league_page(session, d['tier'], d['division'], page_number, api_key)
                results.extend(page_data)
                page_number += 1
            players.extend(results[:count])
            print(f"[INFO] Retrieved {len(results)} players from for {d['tier']} {d['division']}.")

        print("[INFO] Processing all players asynchronously...")
        tasks = [handle_player(session, player, api_key, depth) for player in players]
        results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")

        match_data = []
        for result in results:
            match_data.extend(result)

        total_time = time.time() - start_time
        print(f"[INFO] Finished processing all data in {total_time:.2f} seconds. Total matches: {len(match_data)}")
        print(f"[INFO] Sampled from distribution with depth {depth} and player count {player_count}.")

        return match_data


#------------------------------------------------------------------------------------

async def main(file_path = "test.json", count = 100, depth = 1, flag = 0):
    if flag == '-s':
        print("[INFO] Fetching distribution data...")
        distribution = pd.read_json('rank_distribution_32825.json')
        result = await get_distribution_matches(count, depth, distribution, API_KEY)
        write_json_list(result, file_path)
    
    elif flag == '-v':
        print("[INFO] Fetching division data...")
        result = await get_division_matches(tier = 'DIAMOND', 
                                             division = "II", 
                                             player_count = count,
                                             depth = depth, 
                                             api_key = API_KEY)
        write_json_list(result, file_path)

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python match_collector.py <output_path> <count> <depth> <flag>")
        #flags: 0: division_matches, 1: distribution_matches
        sys.exit(1)
    
    output_path, count, depth, flag = sys.argv[1:]
    count = int(count)
    depth = int(depth)
    asyncio.run(main(output_path, count, depth, flag))
