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

# Hello! This API key has long expired. Please use your own API key.
# You can get one from https://developer.riotgames.com/
API_KEY = "RGAPI-a979a893-3bbd-462c-8ff4-d4cf7daf629c"

RATE_LIMIT = 100
WINDOW = 120  # seconds
REQUEST_INTERVAL = WINDOW / RATE_LIMIT  # 1.2s (for 100 requests per 2 minutes)
MAX_CONCURRENT_REQUESTS = 5

concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
last_request_time = 0
request_lock = Lock()

#----------------------------------------------------------------------------------------------------

def parse_match_data(match_data):
    return match_data

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

async def async_get_timeline_data(session, match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}/timeline?api_key={api_key}"
    return await limited_get(session, url)

#----------------------------------------------------------------------------------------------------

# Gets match datas for a player with a given depth
async def get_player_match_data(session, player_id, api_key, depth):
    puuid_short = player_id['puuid'][:8]
    print(f"[DEBUG] Handling player {puuid_short}...")
    try:
        print(f"[INFO] Fetching match IDs for player {puuid_short}")
        match_ids = await async_get_matches(session, player_id['puuid'], api_key, count=depth)
        print(f"[INFO] Retrieved {len(match_ids)} matches for {puuid_short}")
        print(f"[INFO] Fetching match data for {puuid_short}...")
        tasks = [async_get_match_data(session, match_id, api_key) for match_id in match_ids]
        results = await asyncio.gather(*tasks)
        print(f"[INFO] Parsing match data for {puuid_short}")
        return [parse_match_data(match) for match in results]
    except Exception as e:
        print(f"[ERROR] Failed to process player {puuid_short}: {e}")
        return []

# Gets timeline data for a player with a given depth
async def get_player_timeline_data(session, player_data, api_key, depth):
    puuid_short = player_data['puuid'][:8]
    print(f"[DEBUG] Getting timeline data for {puuid_short}...")
    try:
        print(f"[INFO] Fetching match IDs for player {puuid_short}")
        match_ids = await async_get_matches(session, player_data['puuid'], api_key, count=depth)
        print(f"[INFO] Retrieved {len(match_ids)} matches for {puuid_short}")
        print(f"[INFO] Fetching timeline data for {puuid_short}...")
        tasks = [async_get_timeline_data(session, match_id, api_key) for match_id in match_ids]
        results = await asyncio.gather(*tasks)
        print(f"[INFO] Parsing timeline data for {puuid_short}")
        return [parse_match_data(timeline) for timeline in results]
    except Exception as e:
        print(f"[ERROR] Failed to process player {puuid_short}: {e}")
        return []


#----------------------------------------------------------------------------------------------------

def process_data(results, start_time):
        match_data = []
        for result in results:
            match_data.extend(result)

        total_time = time.time() - start_time
        print(f"[INFO] Finished processing all data in {total_time:.2f} seconds. Total matches: {len(match_data)}")
        
        return match_data

#-------------------------------------------------------------------------------------

# returns a list of player ids on the given tier and division
async def get_players_by_division(session, tier, division, player_count, api_key):
    results = []
    page_number = 1
    print(f"[INFO] Sampling {player_count} players from {tier} {division}...")
    while(len(results) < player_count):
        print(f"[INFO] Fetching league page data no.{len(results)} for {tier} {division}...")
        page_data = await async_get_league_page(session, tier, division, page_number, api_key)
        results.extend(page_data)
        page_number += 1
    return results[:player_count]

async def get_players_from_all_divisions(session, player_count, api_key):
    results = []
    for tier in ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'DIAMOND']:
        for division in ['I', 'II', 'III', 'IV']:
            players = await get_players_by_division(session, tier, division, player_count, api_key)
            results.extend(players)
    for tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
        players = await get_players_by_division(session, tier, 'I', player_count, api_key)
        results.extend(players)
    return results

# returns a list of player ids based on the sampled distribution
async def get_players_distribution(session, distribution, player_count, api_key):
    players = []
    for d in distribution.iloc():
        count = int(np.ceil(d['percentage'] * player_count))
        players.extend(await get_players_by_division(session, d['tier'], d['division'], count, api_key))
    return players

#----------------------------------------------------------------------------------------

# returns a list of match data for the given players
async def get_match_data_from_players(session, players, api_key, depth):
    tasks = [get_player_match_data(session, player, api_key, depth) for player in players]
    results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")
    return results

async def get_timeline_data_from_players(session, players, api_key, depth):
    tasks = [get_player_timeline_data(session, player, api_key, depth) for player in players]
    results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")
    return results

#----------------------------------------------------------------------------------------------------


async def get_timelines_from_all_divisions(session, player_count, depth, api_key):
    print(f"[INFO] Starting async_get_timeline_data | Player Count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_from_all_divisions(session, player_count, api_key)
    results = await get_timeline_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

async def get_timelines_from_division(session, tier, division, player_count, depth, api_key):
    print(f"[INFO] Starting async_get_timeline_data | Tier: {tier}, Division: {division}, Player count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_by_division(session, tier, division, player_count, api_key)
    results = await get_timeline_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

async def get_timelines_from_distribution(session, player_count, depth, distribution, api_key):
    print(f"[INFO] Starting async_get_timeline_data | Player Count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_distribution(session, distribution, player_count, api_key)
    results = await get_timeline_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

async def get_matches_from_all_divisions(session, player_count, depth, api_key):
    print(f"[INFO] Starting async_get_league_data | Player Count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_from_all_divisions(session, player_count, api_key)
    results = await get_match_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

# returns a list of match data for the given division
async def get_matches_from_division(session, tier, division, player_count, depth, api_key):
    print(f"[INFO] Starting async_get_league_data | Tier: {tier}, Division: {division}, Player count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_by_division(session, tier, division, player_count, api_key)
    results = await get_match_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

async def get_matches_from_distribution(session, player_count: int, depth: int, distribution, api_key):
    print(f"[INFO] Starting async_sample_distribution | Player Count: {player_count}, Depth: {depth}")
    start_time = time.time()
    players = await get_players_distribution(session, distribution, player_count, api_key)
    results = await get_match_data_from_players(session, players, api_key, depth)
    return process_data(results, start_time)

#-----------------------------------------------------------------------------------------------------

def parse_common_args(args):
    if len(args) < 3:
        raise ValueError(f"Expected at least {3} arguments, got {len(args)}")
    file_path = args[0]
    try:
        count = int(args[1])
        depth = int(args[2])
    except ValueError:
        raise ValueError("count and depth must be integers")
    print(f"[INFO] File path: {file_path}, Count: {count}, Depth: {depth}")
    return file_path, count, depth

async def main(args):
    flag = args[-1]
    print(f"ARGS: {args[4:6]}")
    print(f"flag: {flag}")

    if flag == '-ta':
        print("[INFO] Fetching timeline data for all divisions...")
        file_path, count, depth = parse_common_args(args[1:])
        async with aiohttp.ClientSession() as session:
            result = await get_timelines_from_all_divisions(session, count, depth, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-tv':
        print("[INFO] Fetching timeline data for a specific division...")
        file_path, count, depth = parse_common_args(args[1:])
        tier, division = args[4:6]
        async with aiohttp.ClientSession() as session:
            result = await get_timelines_from_division(session, tier, division, count, depth, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-ts':
        print("[INFO] Fetching timeline data by distribution...")
        file_path, count, depth = parse_common_args(args[1:])
        distribution = pd.read_json('rank_distribution_32825.json')
        async with aiohttp.ClientSession() as session:
            result = await get_timelines_from_distribution(session, count, depth, distribution, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-ma':
        print("[INFO] Fetching match data for all divisions...")
        file_path, count, depth = parse_common_args(args[1:])
        async with aiohttp.ClientSession() as session:
            result = await get_matches_from_all_divisions(session, count, depth, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-mv':
        print("[INFO] Fetching match data for a specific division...")
        file_path, count, depth = parse_common_args(args[1:])
        tier, division = args[4:6]
        async with aiohttp.ClientSession() as session:
            result = await get_matches_from_division(session, tier, division, count, depth, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-ms':
        print("[INFO] Fetching match data by distribution...")
        file_path, count, depth = parse_common_args(args[1:])
        async with aiohttp.ClientSession() as session:
            distribution = pd.read_json('rank_distribution_32825.json')
            result = await get_matches_from_distribution(session, count, depth, distribution, API_KEY)
            write_json_list(result, file_path)
    elif flag == '-mad':
        tier = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']
        for t in tier:
            if t == 'MASTER' or t == 'GRANDMASTER' or t == 'CHALLENGER':
                division = ['I']
                print(f"[INFO] Fetching match data for {t} {division}...")
                file_path, count, depth = parse_common_args(args[1:])
                async with aiohttp.ClientSession() as session:
                    result = await get_matches_from_division(session, t, division, count, depth, API_KEY)
                    write_json_list(result, f"{file_path}_{t}_{division}.json")
            else:
                division = ['IV', 'III', 'II', 'I']
                for d in division:
                    print(f"[INFO] Fetching match data for {t} {d}...")
                    file_path, count, depth = parse_common_args(args[1:])
                    async with aiohttp.ClientSession() as session:
                        result = await get_matches_from_division(session, t, d, count, depth, API_KEY)
                        write_json_list(result, f"{file_path}_{t}_{d}.json")
            
    else:
        raise ValueError(f"Unknown flag: {flag}")

if __name__ == "__main__":
    asyncio.run(main(sys.argv))
