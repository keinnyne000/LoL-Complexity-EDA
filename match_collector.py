import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import asyncio
import aiohttp
from tqdm.asyncio import tqdm_asyncio

from helpers import write_json, parse_match_data

ACCESS_POINT = "https://americas.api.riotgames.com"
MAX_CALLS_PER_SECOND = 20
MAX_CALLS_PER_TWO_MINUTES = 100

API_KEY = "RGAPI-2b53bd4d-1b21-42ad-a494-0a7bc2bf7892"

#----------------------------------------------------------------------------------------------------

def parse_match_data(match_data):
    return match_data #TODO

def write_json(json, filename):
    with open(filename, 'w') as f:
        f.write(json)

#---------------------------------------------------------------------------------------------

second_semaphore = asyncio.Semaphore(MAX_CALLS_PER_SECOND)
two_minute_semaphore = asyncio.Semaphore(MAX_CALLS_PER_TWO_MINUTES)

async def limited_get(session, url):
    await second_semaphore.acquire()
    await two_minute_semaphore.acquire()
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()

async def rate_limiter():
    async def refill(semaphore, max_tokens, interval):
        while True:
            await asyncio.sleep(interval)
            if(semaphore._value < max_tokens):
                for _ in range(max_tokens - semaphore._value):
                    semaphore.release()

    asyncio.create_task(refill(second_semaphore, MAX_CALLS_PER_SECOND, 1))
    asyncio.create_task(refill(two_minute_semaphore, MAX_CALLS_PER_TWO_MINUTES, 120))
    
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
    async with aiohttp.ClientSession() as session:
        asyncio.create_task(rate_limiter())

        league_data = await async_get_league_page(session, tier, division, page, api_key)
        match_data = []

        async def handle_player(player):
            puuid = player['puuid']
            match_ids = await async_get_matches(session, puuid, api_key, count = depth)
            tasks = [async_get_match_data(session, match_id, api_key) for match_id in match_ids]
            results = await asyncio.gather(*tasks)
            return [parse_match_data(match) for match in results]
                
        tasks = [handle_player(player) for player in league_data]

        #results = await asyncio.gather(*tasks)
        results = await tqdm_asyncio.gather(*tasks, desc="Processing Players")

        for result in results:
            match_data.extend(result)
        
        return match_data

#----------------------------------------------------------------------------------------------------

async def main():
    page_data = await async_get_league_data(tier = 'DIAMOND', 
                                            division = 'IV', 
                                            page = 1, 
                                            depth = 1, 
                                            api_key = API_KEY)
    
    write_json(page_data, 'page_data')

if __name__ == "__main__":
    asyncio.run(main())
