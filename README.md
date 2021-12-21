# rolling-songs: the sliding window playlist statkeeper

say you have some sliding window playlist, which always contains N songs: 
whenever you add one song, you remove another. say you also want stats kept for this list. this app does that for you. 
at the end of the year, you can take these stats and generate a cool poster or something.

here's what I'm doing with it:
- I have a rolling playlist of my favorite 25 songs at a given moment
- I would like to know how that list has progressed over the course of the year (as an exact timeline of substitutions)
- I would like to know which songs were my favorites
- I would like to know my favorite songs by season or month
- I would like to know these things by play count as well as length on playlist

so I'm linking my spotify and last.fm to this app and having it check on things every morning
and record the relevant data to those ends (at least that's the goal). afterwards, I'll make a 
cool "better spotify wrapped" graphic or poster or something with the data. if I finish this and 
make a template I'll link it here so others can use it too.

## usage
1. clone this repo with ```git clone git@github.com:michaeljecmen/rolling-songs.git```
2. run ```pip install spotipy pylast```
3.  ```cp example.json config.json``` and modify all of the fields except the spotify url. to find your spotify client id and client secret, head over to [the spotify dev dashboard](https://developer.spotify.com/dashboard/), log in, and create an application. to find your lastfm api key and shared secret, head
over to [the lastfm dev dashboard](https://www.last.fm/api/accounts), create a dev account (or make your normal account a dev account), create an application, and copy over your credentials. to be clear, modify the fields in ```config.json```, not ```example.json```.
4. for the app you just created on your spotify dev dashboard, add the url ```http://localhost:8888/callback``` to the list of callbacks using the "edit settings" button. this url should match the url in your ```config.json```, so if you edited that for whatever reason be sure to update your callback list on the dashboard to match.
5. run the program once with ```python3 rolling.py``` and authenticate the app when it opens a browser window and yells at you. you should be auth'd for a while (no idea how long the tokens last).
5. run the program once a day (or whenever you make changes to your playlist) with ```python3 rolling.py```, or, even better, set up a cron job on a box somewhere.
