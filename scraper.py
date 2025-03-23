import time
import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt

ACCESS_POINT = "https://americas.api.riotgames.com"


#----------------------------------------------------------------------------------------------------
#Rate Limits
#20 requests every 1 seconds(s)
#100 requests every 2 minutes(s)

def api_get_puuid(name, tag, api_key):
    url = f"{ACCESS_POINT}/riot/account/v1/accounts/by-riot-id/{name}/{tag}?api_key={api_key}"
    data = request_data(url)
    return data['puuid']

def api_get_matches(puuid, api_key, count = 100):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&api_key={api_key}"
    data = request_data(url)
    return data

def api_get_match_data(match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}?api_key={api_key}"
    data = request_data(url)
    return data

def api_get_league_entries(tier, division, page, api_key):
    # tier: IRON, BRONZE, SILVER, GOLD, PLATINUM, DIAMOND, MASTER, GRANDMASTER, CHALLENGER
    # division: I, II, III, IV
    url = f"{ACCESS_POINT}/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}&api_key={api_key}"
    data = request_data(url)
    return data

#----------------------------------------------------------------------------------------------------

def request_data(url):
    retries = 0
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status() 

def parse_match_data(match_data):
    return match_data #TODO

# gets all the parsed match data on a page of a division tier page
#! can easily exceed rate limit
def get_tier_page_data(tier, division, page, api_key):
    league_data = api_get_league_entries(tier, division, page, api_key)
    match_data = []
    for player in league_data['entries']:
        puuid = player['puuid']
        match_ids = api_get_matches(puuid, api_key, count = 20)
        for match_id in match_ids:
            match_data.append(parse_match_data(api_get_match_data(match_id, api_key)))
    return match_data 

def write_json(json, filename):
    with open(filename, 'w') as f:
        f.write(json)


def main():
    name = "KEEN NEENE"
    tag = "NA1"
    api_key = "RGAPI-0a097368-5f20-4c89-bdf8-6a75789ac231"

    division = 'DIAMOND'
    tier = 'IV'
    page = 1

    page_data  = get_tier_page_data(division, tier, page, api_key)
    write_json(page_data, 'page_data')

if __name__ == '__main__':
    main()

