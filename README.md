# ngs_vid_dl

OVERVIEW:
auto dl recent vids and renames files into a standard format and packages as mkv maintianing chapters and other metadata if present

it also saves a copy of the html source and the setlist (if present) to a folder in the script_data_directory



SETUP:
you need to put a username and pasword into the config ini

thats the only necessary change, all the rest of the settings can be let as is (or changed)

if you leave the paths blank it will creat folders in the directory from which the script is run. there are examples of paths in the examples folder.

the processed_files.txt keeps track of what files have been processed to avoid duplication, the script also adds and videos in the video folder path to the list to skip. you can choose whether or not to use this by placing the processed_text file in the root, or not.

if chromedriver isnt matchign get them here.
chrome binary and chromedriver.exe (same version):
https://googlechromelabs.github.io/chrome-for-testing/#stable


USE:
just running the script will loop through all recent/exclusive

argument "--page-url" [URL]
[URL] Can be:
"videos"  - get all recent 
"livestreams" - get all exclusive
or link to specific release
