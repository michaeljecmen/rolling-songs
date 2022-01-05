#!/usr/bin/python3

import sys
import os
import json
from pathlib import Path

import spotipy

from helpers.date import get_date, is_ts_before_yesterday
from helpers.config import get_config
from helpers.gmail import send_gmail
from helpers.lastfm import get_lastfm_network
from helpers.log import append_to_log

# debug flag
debug = False

def debug_print(*args, **kwargs):
    if debug:
        print(*args, **kwargs)

def create_data_dir_if_dne(config):
    if not os.path.exists(config["DATA_DIR"]):
        os.makedirs(config["DATA_DIR"])

def authenticate_services(config):
    # will require you to sign in via a browser the first time you launch this
    token = spotipy.util.prompt_for_user_token(
        config["SPOTIFY_USERNAME"],
        "user-library-read",
        config["SPOTIFY_CLIENT_ID"],
        config["SPOTIFY_CLIENT_SECRET"],
        config["SPOTIFY_REDIRECT_URI"]
    )
    spotify = spotipy.Spotify(auth=token)

    network = get_lastfm_network(config)
    
    return spotify, network.get_authenticated_user()

# returns list of { "name": trackname, "artists": [artists], "album": album }
# containing each song in the spotify playlist provided
def get_rolling_tracklist(config, spotify):
    spotify_username = config["SPOTIFY_USERNAME"]
    playlists = spotify.user_playlists(spotify_username)
    tracklist = []
    for playlist in playlists['items']:

        if playlist['owner']['id'] != spotify_username:
            continue

        if playlist['name'] != config["SPOTIFY_PLAYLIST"]:
            continue
        
        # found the rolling playlist
        results = spotify.playlist(playlist['id'], fields="tracks,next")
        spotify_tracks = results['tracks']
        while spotify_tracks:
            # not quite sure why the for loop is needed here
            for item in spotify_tracks['items']:
                spotify_track = item['track']
                track = {
                    "name": spotify_track['name'],
                    "artists": [ artist['name'] for artist in spotify_track['artists'] ],
                    "album": spotify_track['album']['name']
                }
                tracklist.append(track)
                
            spotify_tracks = spotify.next(spotify_tracks)
        
        # can only be one rolling playlist
        break

    return tracklist

def file_exists(filename):
    return Path(filename).exists()

# load previous tracklist from json file in config
def load_previous_tracklist(config):
    if not file_exists(config["DATA_DIR"] + config["STORAGE_FILENAME"]):
        debug_print("first time running this program, previous tracklist not stored yet")
        return {}

    with open(config["DATA_DIR"] + config["STORAGE_FILENAME"], "r") as trackfile:
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

# for each new track, get number of plays at present and store.
# for each track which was removed from tracklist, get number of plays
# at present and deduct plays when added to get plays since added.
# returns updated tracklist, removed tracks as a pair
def update_tracklist(new_tracklist, tracklist, lastfm):
    # separate new tracks and kept tracks
    news = []
    kept = []
    for new_track in new_tracklist:
        existing_track = get_corresponding_track(tracklist, new_track)
        if existing_track is None:
            news.append(new_track)
        else:
            kept.append(existing_track)

    # now repeat in reverse to find removed tracks
    removed = []
    for existing_track in tracklist:
        if get_corresponding_track(new_tracklist, existing_track) is None:
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
        track["playcount"] = len([s for s in scrobs if is_ts_before_yesterday(int(s.timestamp)) ])
        kept.append(track)
        message += "[+] " + track["name"] + " by " + str(track["artists"]) + '\n'

    # kept is now the updated current tracklist
    return kept, removed, news, message

# if it does not already exist, create logfile
def create_logfile(config, tracklist):
    if file_exists(config["DATA_DIR"] + config["LOG_FILENAME"]):
        return

    # create logfile and store current 25 tracks in it
    with open(config["DATA_DIR"] + config["LOG_FILENAME"], "w") as logfile:
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
    with open(config["DATA_DIR"] + config["STORAGE_FILENAME"], "w") as tfile:
        json.dump(tracklist, tfile, indent=4)
    
def debug_print_and_email_message(config, subject, content):
    if content != "":
        send_gmail(config["SENDER_EMAIL"], config["SENDER_PASSWORD"], config["RECEIVER_EMAIL"], subject, content)
        debug_print(content)

def main():
    config = get_config()
    spotify, lastfm = authenticate_services(config)

    # get current tracks and compare to previously stored tracks
    tracklist = get_rolling_tracklist(config, spotify)

    # read previous tracklist from storage file
    previous_tracklist = load_previous_tracklist(config)

    # get diff and update playcounts for new and removed songs
    tracklist, removed, added, message = update_tracklist(tracklist, previous_tracklist, lastfm)

    # write the tracklist file to be checked next time,
    # creating the data dir if it does not yet exist
    create_data_dir_if_dne(config)
    write_tracklist_file(config, tracklist)

    # ...and update logfile, creating it if dne
    create_logfile(config, tracklist)
    append_to_log(config, removed, added)

    # finally, log the message and email it to the user
    debug_print_and_email_message(config, "your rolling playlist was updated!", message)
    
if __name__ == '__main__':
    # debug printing on for any invocation with more than the required args
    if len(sys.argv) > 1:
        debug = True
    main()