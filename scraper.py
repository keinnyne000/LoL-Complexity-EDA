import time
import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt

ACCESS_POINT = "https://americas.api.riotgames.com"

#Rate Limits
#20 requests every 1 seconds(s)
#100 requests every 2 minutes(s)

def get_puuid(name, tag, api_key):
    url = f"{ACCESS_POINT}/riot/account/v1/accounts/by-riot-id/{name}/{tag}?api_key={api_key}"
    data = request_data(url)
    return data['puuid']

def get_matches(puuid, api_key, count = 100):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&api_key={api_key}"
    data = request_data(url)
    return data

def get_match_data(match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}?api_key={api_key}"
    data = request_data(url)
    return data

def request_data(url):
    retries = 0
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status() 


# Steps:
# get puuid of entry point player
# get last 100 matches of entry point player
# save match data from matches
# get puuid of all players in matches
# use each player as an entry point
def get_match_datas(name, tag, api_key, count):
    puuid = get_puuid(name, tag, api_key)
    matches = get_matches(puuid, api_key, count = count)
    match_data = []
    for match in matches:
        match_data.append(get_match_data(match, api_key))

    return match_data

def write_match_data(match_data, filename):
    with open(filename, 'w') as f:
        f.write(match_data)

def main():
    name = "KEEN NEENE"
    tag = "NA1"
    api_key = "RGAPI-1d07c8da-8fa3-4dd3-beec-817588a8a670"
    match_data = get_match_datas(name, tag, api_key, count = 100)
    write_match_data(match_data, "match_data.json")

if __name__ == '__main__':
    main()

