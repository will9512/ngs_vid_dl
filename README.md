# nugs_vid_dl

OVERVIEW:

this is just a fancy wrapper for https://github.com/Sorrow446/Nugs-Downloader

-auto finds and dl recently available livestreams and videos (or whatever you link to ex. artist page or single vid)

-copys the .ts file into mkv (chapters and other metadata maintained if present)

-renames files into a standard format:
    artist date(yyyy-mm-dd) venue, location resolution

-saves some data to a script_data_directory namely:
    a copy of the html source
 	the setlist (if present)
    the cover image.jpg
	



SETUP:

the only necessary step is to put a username and pasword for nugs into the config ini. (the free trial works)


if you leave the paths blank it will creat folders in the directory from which the script is run. there are examples of paths in the examples folder.

update chrome

if chromedriver isnt matchign get them here, chrome binary and chromedriver.exe (same version):

https://googlechromelabs.github.io/chrome-for-testing/#stable




USE:
you can just run the script, or pass:

    "--page-url" [URL]

[URL] passed can be:

    - "watch" - download vids from 'https://play.nugs.net/watch/videos/recent'

    - "exclusive" - download vids from 'https://play.nugs.net/watch/livestreams/recent'

    - any single release (or a list) ex:
        - https://play.nugs.net/watch/livestreams/exclusive/35973
        - https://play.nugs.net/watch/release/33516
	- https://play.nugs.net/watch/release/33516 https://play.nugs.net/watch/livestreams/exclusive/35973

    - an artist page with 'browse' subbed for 'watch' will download all vids form that artist ex:
        - instead of https://play.nugs.net/browse/artist/128
        - use https://play.nugs.net/browse/artist/128

    - blank (no arg passed) does both "watch" and "exclusive"

example use:

nugs_vid_dl --page-url watch



NOTES:
the processed_files.txt keeps track of what files have been processed to avoid duplication, the script also adds and videos in the video folder path to the list to skip. you can choose whether or not to use this by placing the processed_text file in the root, or not.

if it gives selenium erros try just running it again

exclusive fimenames are messed up sometimes. nugs has no naming convention for the shows they put up as replays




use approperiatly with regards to your account
