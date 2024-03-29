#!/usr/bin/python3
# run "which python3" in your terminal and
# replace "/usr/bin/python3" above with the output

import sys
import os
import json
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from helpers.cache import ConfigCacheHandler
from helpers.date import get_date, is_ts_before_yesterday
from helpers.config import read_config, get_absolute_rolling_songs_dir
from helpers.gmail import send_gmail
from helpers.lastfm import get_lastfm_network
from helpers.log import append_to_log

# debug flag
debug = False

def debug_print(*args, **kwargs):
    if debug:
        print(*args, **kwargs) 
        
# TODO at end of month dump top 10 for the month into timelapse/month-year playlist

def create_data_dir_if_dne(config):
    data_dir_path = get_absolute_rolling_songs_dir() + config["DATA_DIR"]
    if not os.path.exists(data_dir_path):
        os.makedirs(data_dir_path)

def authenticate_services(config):
    oauth = SpotifyOAuth(client_id=config["SPOTIFY_CLIENT_ID"], client_secret=config["SPOTIFY_CLIENT_SECRET"], redirect_uri=config["SPOTIFY_REDIRECT_URI"], cache_handler=ConfigCacheHandler())
    spotify = spotipy.Spotify(oauth_manager=oauth)

    network = get_lastfm_network(config)
    
    return spotify, network.get_authenticated_user()

# given a playlist, returns the full tracklist as a dict of uri->{name artists album}
def fetch_full_tracklist(spotify, playlist):
    tracklist = {}
    results = spotify.playlist(playlist['id'], fields="tracks,next")
    spotify_tracks = results['tracks']
    while spotify_tracks:
        # not quite sure why the for loop is needed here
        for item in spotify_tracks['items']:
            spotify_track = item['track']
            tracklist[spotify_track['uri']] = {
                "name": spotify_track['name'],
                "artists": [ artist['name'] for artist in spotify_track['artists'] ],
                "album": spotify_track['album']['name'],
                "uri": spotify_track['uri'],
            }
            
        spotify_tracks = spotify.next(spotify_tracks)
        
    return tracklist

# returns list of { "name": trackname, "artists": [artists], "album": album }
# containing each song in the spotify playlist provided
# also returns the tracklist from the log playlist and its playlist id
def get_rolling_tracklist(config, spotify):
    spotify_username = config["SPOTIFY_USERNAME"]
    playlists = {"items":["sentinel"]}
    tracklist = {}
    log_tracklist = {}
    log_playlist_id = ""
    rolling_found = False
    offset = 0
    while len(playlists['items']) > 0:
        playlists = spotify.user_playlists(spotify_username, limit=50, offset=offset)
        offset += 50
        for playlist in playlists['items']:

            # defense against taking another user's "rolling" playlist that you have liked
            # not sure if this is even possible but why not
            if playlist['owner']['id'] != spotify_username:
                continue

            # only want to request the playlists once, so need to check
            # for the log playlist and the rolling playlist here and remember
            # the log playlist id
            if playlist['name'] == config["SPOTIFY_LOG_PLAYLIST"]:
                log_playlist_id = playlist['uri']
                log_tracklist = fetch_full_tracklist(spotify, playlist)
                
                # break if we've found both now
                if rolling_found:
                    return tracklist, log_tracklist, log_playlist_id

            if playlist['name'] == config["SPOTIFY_PLAYLIST"]:
                # actually get the songs
                tracklist = fetch_full_tracklist(spotify, playlist)
            
                # break if we've found both now
                if log_playlist_id != "":
                    return tracklist, log_tracklist, log_playlist_id
            
                # now as soon as we find the rolling playlist, we can break
                rolling_found = True

    print("rolling playlist not found")
    exit(1)

def file_exists(filename):
    return Path(filename).exists()

# load previous tracklist from json file in config
def load_previous_tracklist(config):
    tracklist_filename = get_absolute_rolling_songs_dir() + config["DATA_DIR"] + config["STORAGE_FILENAME"]
    if not file_exists(tracklist_filename):
        debug_print("first time running this program, previous tracklist not stored yet")
        return {}

    with open(tracklist_filename, "r") as trackfile:
        return json.load(trackfile)

def are_tracks_same(new, old):
    # new have "name", "artists", and "album" fields
    # old have "name", "artists", "album", and "playcount" fields
    if new["name"] != old["name"]:
        return False
    if new["artists"] != old["artists"]:
        return False
    if new["album"] != old["album"]:
        return False

    return True

# linear, who cares. returns track or None if not found
def get_corresponding_track(tracklist, track):
    for corresponding_track in tracklist:
        if are_tracks_same(corresponding_track, track):
            return corresponding_track
    return None

# adds the tracks passed to the log playlist on the users' spotify account
def add_tracks_to_log_playlist(config, spotify, log_playlist_id, new_tracks):
    if len(new_tracks) == 0:
        return
    
    track_uris = [ track['uri'] for track in new_tracks ]
    spotify.user_playlist_add_tracks(config["SPOTIFY_USERNAME"], playlist_id=log_playlist_id, tracks=track_uris)

# for each new track, get number of plays at present and store.
# for each track which was removed from tracklist, get number of plays
# at present and deduct plays when added to get plays since added.
# returns updated tracklist, removed tracks as a pair
def update_tracklist(new_tracklist, tracklist, lastfm):
    # separate new tracks and kept tracks
    news = []
    kept = []
    for new_track in new_tracklist.values():
        existing_track = get_corresponding_track(tracklist, new_track)
        if existing_track is None:
            news.append(new_track)
        else:
            kept.append(existing_track)

    # now repeat in reverse to find removed tracks
    removed = []
    for existing_track in tracklist:
        if get_corresponding_track(new_tracklist.values(), existing_track) is None:
            # this track must have been removed since we last checked
            removed.append(existing_track)

    # prepare simple log message to email user
    message = ""

    # go through olds, update playcounts and timestamp out
    for track in removed:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs) - track["playcount"]
        message += "[-] " + track["name"] + " by " + str(track["artists"]) + ", " + str(track["playcount"]) + " plays since added\n"

    # go through news, set playcounts and timestamp in, and append to kept
    for track in news:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])

        # only track plays before yesterday (plays on day the track was added count towards pc)
        track["playcount"] = len([s for s in scrobs if is_ts_before_yesterday(int(s.timestamp)) ])
        kept.append(track)
        message += "[+] " + track["name"] + " by " + str(track["artists"]) + '\n'

    # kept is now the updated current tracklist
    return kept, removed, news, message

# if poss_dupes entry (list of uris) exists in dic, 
# do not add to the final list 
def prune_duplicates(poss_dupes, dic):
    out = []
    for elt in poss_dupes:
        if elt['uri'] not in dic.keys():
            out.append(elt)
            
    return out
    
# if it does not already exist, create logfile
def create_logfile(config, tracklist):
    logfilename = get_absolute_rolling_songs_dir() + config["DATA_DIR"] + config["LOG_FILENAME"]
    if file_exists(logfilename):
        return

    # create logfile and store current 25 tracks in it
    with open(logfilename, "w") as logfile:
        # playcount is redundant in logfile
        for track in tracklist:
            track.pop("playcount")

        # init must be a list so changelog can be appended to it later
        init = [{
            "date": get_date(),
            "starting_tracks": tracklist
        }]

        logfile.write(json.dumps(init, indent=4))

def write_tracklist_file(config, tracklist):
    with open(get_absolute_rolling_songs_dir() + config["DATA_DIR"] + config["STORAGE_FILENAME"], "w") as tfile:
        json.dump(tracklist, tfile, indent=4)
    
def debug_print_and_email_message(config, subject, content):
    if content != "":
        send_gmail(config["SENDER_EMAIL"], config["SENDER_PASSWORD"], config["RECEIVER_EMAIL"], subject, content)
        debug_print(content)

def main():
    config = read_config()
    spotify, lastfm = authenticate_services(config)

    # get current tracks and compare to previously stored tracks
    tracklist, log_tracklist, log_playlist_id = get_rolling_tracklist(config, spotify)

    # read previous tracklist from storage file
    previous_tracklist = load_previous_tracklist(config)

    # get diff and update playcounts for new and removed songs
    tracklist, removed, added, message = update_tracklist(tracklist, previous_tracklist, lastfm)

    # if a song makes it on the rolling playlist more than once, do not add it after the first time
    # in other words, do not add songs to the log playlist that are already on it
    added = prune_duplicates(added, log_tracklist)

    # update the spotify log playlist with the songs that were added
    add_tracks_to_log_playlist(config, spotify, log_playlist_id, added)
    
    # write the tracklist file to be checked next time,
    # creating the data dir if it does not yet exist
    create_data_dir_if_dne(config)
    write_tracklist_file(config, tracklist)

    # ...and update logfile, creating it if dne
    create_logfile(config, tracklist)
    append_to_log(config, removed, added)

    # finally, log the message and email it to the user (disabled 10/5/22 mjj)
    # debug_print_and_email_message(config, "your rolling playlist was updated!", message)
    
if __name__ == '__main__':
    # debug printing on for any invocation with more than the required args
    if len(sys.argv) > 1:
        debug = True
    main()
