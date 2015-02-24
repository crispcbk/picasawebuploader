picasawebuploader
=================

A script that uploads photos to Google+ / Picasa Web Albums. The original script
written by Jackpal, see: https://github.com/jackpal/picasawebuploader

Features:
+ Resizes large images to be less than the free limit (2048 x 2048)
+ Uploads all directories under a given directory
+ Restartable
+ Creates the albums as "private" aka "limited"
+ Automatically retries when Google data service errors out.
+ Runs under various OS's (tested under Windows & Synology NAS)
+ RegEx based skipping of directories
+ Can be used to copy also metadata from local pictures to Picasa


To Do
-----

+ Use multiple threads for uploading.
+ Add Progress UI
+ Deal with duplicate picture and folder names, both on local and web collections.
  + Currently we just throw an exception when we detect duplicate names.
+ Deal with 'Error: 17 REJECTED_USER_LIMIT' errors.
+ Performance enhancement: check metadata differences before updating
+ Synchronization of people tags from local to Picasa
+ Synchronization of people tags from Picasa to local?

Installation
------------

+ Prerequisites:
  + Python 2.7
  + Google Data APIs http://code.google.com/apis/gdata/
    + gdata-2.0.16 for Python
  + The PIL library for Python or BSD "sips" image processing program.
	+ PIL is available on most UNIX like systems.
    + "sips" comes pre-installed on OSX.
  + pyexiv2 module for writing correct EXIF data, or 'exiftool'

Known Problems
--------------

Picasa Web Albums appears to have an undocumented upload quota system that
limits uploads to a certain number of bytes per month.

Do a web search for REJECTED_USER_LIMIT to see the various discussions about
this. From reading the web forums it appears that the upload quota is reset
occasionally (possibly monthly). If you start getting REJECTED_USER_LIMIT
errors when you run this script you may have to wait a month to upload new
pictures.

Some people have reported that paying for yearly web storage will remove the
upload quota.
