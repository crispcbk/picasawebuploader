#! /usr/bin/python
#
# Upload directories of videos and pictures to Picasa Web Albums
#
# Requires:
#   Python 2.7
#   gdata 2.0 python library
#   PIL or sips command-line image processing tools.
#
# Copyright (C) 2011 Jack Palevich, All Rights Reserved
# Additions performed by CRiSP in 2015
#
# Contains code from http://nathanvangheem.com/news/moving-to-picasa-update

#
# TODO:
# - implement uploading only metadata (also for existing files), e.g. "--forcemetadata" option 
#      -> this needs to work on the syncDirs() method which is called for files that exist in both locations

import sys
if sys.version_info < (2,7):
    sys.stderr.write("This script requires Python 2.7 or newer.\n")
    sys.stderr.write("Current version: " + sys.version + "\n")
    sys.stderr.flush()
    sys.exit(1)

import argparse
#import atom
#import atom.service
import filecmp
import gdata
import gdata.photos.service
import gdata.media
import gdata.geo
import getpass
import os
import tempfile
import time
import subprocess
import re
import PIL

from gdata.photos.service import atom, GPHOTOS_INVALID_ARGUMENT, GPHOTOS_INVALID_CONTENT_TYPE, GooglePhotosException

PICASA_MAX_FREE_IMAGE_DIMENSION = 2048
PICASA_MAX_VIDEO_SIZE_BYTES = 104857600

# global variables
skipdirs = None


# Try to import PIL if installed
try:
    from PIL import Image
    HAS_PIL_IMAGE = True
except:
    HAS_PIL_IMAGE = False

# Try to import PY_EXIV2 if installed
try:
    import pyexiv2
    HAS_PYEXIV2 = True
except:
    HAS_PYEXIV2 = False


# Finds an executable on linux or windows PATH with a specific name
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    
    if (sys.platform == 'win32'):
        prog = program + '.exe'
    else:
        prog = program
    
    fpath, fname = os.path.split(prog)
    if fpath:
        if is_exe(prog):
            return prog
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, prog)
            if is_exe(exe_file):
                return exe_file
    
    return None

# Try to find EXIFTOOL if installed
exifTool = which('exiftool')
if (exifTool is not None):
    print '*** exiftool found at: ' + exifTool
    HAS_EXIF = True
else:
    HAS_EXIF = False

# Try to find SIPS if installed
sipsTool = which('sips')
if (sipsTool is not None):
    print '*** sips found at: ' + sipsTool
    HAS_SIPS = True
else:
    HAS_SIPS = False
    
    
    
class VideoEntry(gdata.photos.PhotoEntry):
    pass

gdata.photos.VideoEntry = VideoEntry

def InsertVideo(self, album_or_uri, video, filename_or_handle, content_type='image/jpeg'):
    """Copy of InsertPhoto which removes protections since it *should* work"""
    try:
        assert(isinstance(video, VideoEntry))
    except AssertionError:
        raise GooglePhotosException({'status':GPHOTOS_INVALID_ARGUMENT,
            'body':'`video` must be a gdata.photos.VideoEntry instance',
            'reason':'Found %s, not PhotoEntry' % type(video)
        })
    try:
        majtype, mintype = content_type.split('/')
        #assert(mintype in SUPPORTED_UPLOAD_TYPES)
    except (ValueError, AssertionError):
        raise GooglePhotosException({'status':GPHOTOS_INVALID_CONTENT_TYPE,
            'body':'This is not a valid content type: %s' % content_type,
            'reason':'Accepted content types:'
        })
    if isinstance(filename_or_handle, (str, unicode)) and \
        os.path.exists(filename_or_handle): # it's a file name
        mediasource = gdata.MediaSource()
        mediasource.setFile(filename_or_handle, content_type)
    elif hasattr(filename_or_handle, 'read'):# it's a file-like resource
        if hasattr(filename_or_handle, 'seek'):
            filename_or_handle.seek(0) # rewind pointer to the start of the file
        # gdata.MediaSource needs the content length, so read the whole image
        file_handle = StringIO.StringIO(filename_or_handle.read())
        name = 'image'
        if hasattr(filename_or_handle, 'name'):
            name = filename_or_handle.name
        mediasource = gdata.MediaSource(file_handle, content_type,
            content_length=file_handle.len, file_name=name)
    else: #filename_or_handle is not valid
        raise GooglePhotosException({'status':GPHOTOS_INVALID_ARGUMENT,
            'body':'`filename_or_handle` must be a path name or a file-like object',
            'reason':'Found %s, not path name or object with a .read() method' % \
            type(filename_or_handle)
        })

    if isinstance(album_or_uri, (str, unicode)): # it's a uri
        feed_uri = album_or_uri
    elif hasattr(album_or_uri, 'GetFeedLink'): # it's a AlbumFeed object
        feed_uri = album_or_uri.GetFeedLink().href

    try:
        return self.Post(video, uri=feed_uri, media_source=mediasource,
            converter=None)
    except gdata.service.RequestError, e:
        raise GooglePhotosException(e.args[0])

gdata.photos.service.PhotosService.InsertVideo = InsertVideo

def login(email, password):
    gd_client = gdata.photos.service.PhotosService()
    gd_client.email = email
    gd_client.password = password
    gd_client.source = 'palevich-photouploader'
    gd_client.ProgrammaticLogin()
    return gd_client

def protectWebAlbums(gd_client):
    albums = gd_client.GetUserFeed()
    for album in albums.entry:
        # print 'title: %s, number of photos: %s, id: %s summary: %s access: %s\n' % (album.title.text,
        #  album.numphotos.text, album.gphoto_id.text, album.summary.text, album.access.text)
        needUpdate = False
        if album.summary.text == 'test album':
            album.summary.text = ''
            needUpdate = True
        if album.access.text != 'private':
            album.access.text = 'private'
            needUpdate = True
        # print album
        if needUpdate:
            print "updating " + album.title.text
            try:
                updated_album = gd_client.Put(album, album.GetEditLink().href,
                        converter=gdata.photos.AlbumEntryFromString)
            except gdata.service.RequestError, e:
                print "Could not update album: " + str(e)

def getWebAlbums(gd_client):
    albums = gd_client.GetUserFeed()
    d = {}
    for album in albums.entry:
        title = album.title.text
        if title in d:
          print "Duplicate web album:" + title
        else:
          d[title] = album
        # print 'title: %s, number of photos: %s, id: %s' % (album.title.text,
        #    album.numphotos.text, album.gphoto_id.text)
        #print vars(album)
    return d

def findAlbum(gd_client, title):
    albums = gd_client.GetUserFeed()
    for album in albums.entry:
        if album.title.text == title:
            return album
    return None

def createAlbum(gd_client, title):
    print "Creating album " + title
    # public, private, protected. private == "anyone with link"
    album = gd_client.InsertAlbum(title=title, summary='', access='private')
    return album

def findOrCreateAlbum(gd_client, title):
    delay = 1
    while True:
        try:
            album = findAlbum(gd_client, title)
            if not album:
                album = createAlbum(gd_client, title)
            return album
        except gdata.photos.service.GooglePhotosException, e:
            print "caught exception " + str(e)
            print "sleeping for " + str(delay) + " seconds"
            time.sleep(delay)
            delay = delay * 2

def postPhoto(gd_client, album, filename):
    album_url = '/data/feed/api/user/%s/albumid/%s' % (gd_client.email, album.gphoto_id.text)
    photo = gd_client.InsertPhotoSimple(album_url, 'New Photo',
            'Uploaded using the API', filename, content_type='image/jpeg')
    return photo

def postPhotoToAlbum(gd_client, photo, album):
    album = findOrCreateAlbum(gd_client, args.album)
    photo = postPhoto(gd_client, album, args.source)
    return photo

def getWebPhotosForAlbum(gd_client, album):
    photos = gd_client.GetFeed(
            '/data/feed/api/user/%s/albumid/%s?kind=photo' % (
            gd_client.email, album.gphoto_id.text))
    return photos.entry

allExtensions = {}

# key: extension, value: type
knownExtensions = {
    '.png': 'image/png',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.avi': 'video/avi',
    '.wmv': 'video/wmv',
    '.3gp': 'video/3gp',
    '.m4v': 'video/m4v',
    '.mp4': 'video/mp4',
    '.mov': 'video/mov'
    }

def getContentType(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in knownExtensions:
        return knownExtensions[ext]
    else:
        return None

def accumulateSeenExtensions(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in allExtensions:
        allExtensions[ext] = allExtensions[ext] + 1
    else:
        allExtensions[ext] = 1

def isMediaFilename(filename):
    accumulateSeenExtensions(filename)
    return getContentType(filename) != None

def visit(arg, dirname, names):
    # arg is the "hash" supplied in the "os.path.walk" call
    # dirname is the directory we are walking into
    # names is the content of the directory which we are free to modify to prevent it being crawled further
    
    # Skip hidden folders
    basedirname = os.path.basename(dirname)
    if basedirname.startswith('.'):
        # We skip this directory and everything underneath
        del names[:]
        return
    
     # Skip folders defined by user
    if skipdirs is not None:
        # Iterate over the list
        for regex in skipdirs:
            if re.match(regex, basedirname, re.M|re.I):
                # We skip this directory and everything underneath
                del names[:]
                return

    # Find all mediafiles that are:
    #  - not hidden files
    #  - are a known media extension type
    #  - are actual files (not directories)
    mediaFiles = [name for name in names if not name.startswith('.') and isMediaFilename(name) and
        os.path.isfile(os.path.join(dirname, name))]
    count = len(mediaFiles)
    if count > 0:
        arg[dirname] = {'files': sorted(mediaFiles)}

def findMedia(source):
    hash = {}
    # Run over all files, calling the "visit" function for every file encountered, passing "hash" array as an argument to the visit function
    os.path.walk(source, visit, hash)
    return hash

def findDupDirs(photos):
    d = {}
    for i in photos:
        base = os.path.basename(i)
        if base in d:
            print "duplicate " + base + ":\n" + i + ":\n" + d[base]
            dc = filecmp.dircmp(i, d[base])
            print dc.diff_files
        d[base] = i
    # print [len(photos[i]['files']) for i in photos]

def toBaseName(photos):
    # Create a mapping between a pathname and an album name
    d = {}
    for i in photos:
        base = os.path.basename(i)
        if base in d:
            print "duplicate " + base + ":\n" + i + ":\n" + d[base]['path']
            raise Exception("duplicate base")
        p = photos[i]
        p['path'] = i
        d[base] = p
    return d

def compareLocalToWeb(local, web):
    localOnly = []
    both = []
    webOnly = []
    for i in local:
        if i in web:
            both.append(i)
        else:
            localOnly.append(i)
    for i in web:
        if i not in local:
            webOnly.append(i)
    return {'localOnly' : localOnly, 'both' : both, 'webOnly' : webOnly}

def compareLocalToWebDir(localAlbum, webPhotoDict):
    localOnly = []
    both = []
    webOnly = []
    for i in localAlbum:
        if i in webPhotoDict:
            both.append(i)
        else:
            localOnly.append(i)
    for i in webPhotoDict:
        if i not in localAlbum:
            webOnly.append(i)
    return {'localOnly' : localOnly, 'both' : both, 'webOnly' : webOnly}

def syncDirs(gd_client, dirs, local, web, no_resize):
    for dir in dirs:
        syncDir(gd_client, dir, local[dir], web[dir], no_resize)

def syncDir(gd_client, dir, localAlbum, webAlbum, no_resize):
    webPhotos = getWebPhotosForAlbum(gd_client, webAlbum)
    webPhotoDict = {}
    
    # Filter out duplicates in the web album
    for photo in webPhotos:
        title = photo.title.text
        if title in webPhotoDict:
            print "duplicate web photo: " + webAlbum.title.text + " " + title
        else:
            webPhotoDict[title] = photo
            
    # Now that we have unique list of web photos (duplicates filtered), compare
    # with the files we have locally for that album...
    report = compareLocalToWebDir(localAlbum['files'], webPhotoDict)
    localOnly = report['localOnly']
    # Upload all files that we have locally only
    for f in localOnly:
        localPath = os.path.join(localAlbum['path'], f)
        upload(gd_client, localPath, webAlbum, f, no_resize)

def uploadDirs(gd_client, dirs, local, no_resize):
    for dir in dirs:
        uploadDir(gd_client, dir, local[dir], no_resize)

def uploadDir(gd_client, dir, localAlbum, no_resize):
    webAlbum = findOrCreateAlbum(gd_client, dir)
    for f in localAlbum['files']:
        localPath = os.path.join(localAlbum['path'], f)
        upload(gd_client, localPath, webAlbum, f, no_resize)

# Global used for a temp directory
gTempDir = ''

def getTempPath(localPath):
    baseName = os.path.basename(localPath)
    global gTempDir
    if gTempDir == '':
        gTempDir = tempfile.mkdtemp('imageshrinker')
    tempPath = os.path.join(gTempDir, baseName)
    return tempPath

def imageMaxDimension(path):
    if HAS_PIL_IMAGE:
        return imageMaxDimensionByPIL(path)
    elif HAS_SIPS:        
        output = subprocess.check_output([sipsTool, '-g', 'pixelWidth', '-g', 'pixelHeight', path])
        lines = output.split('\n')
        w = int(lines[1].split()[1])
        h = int(lines[2].split()[1])
        return max(w,h)
    return 0

def imageMaxDimensionByPIL(path):
  img = Image.open(path)
  (w,h) = img.size
  return max(w,h)

def shrinkIfNeeded(path, maxDimension):
    # Shrinking is only support if we have PIL or SIPS
    if (HAS_PIL_IMAGE):
        return shrinkIfNeededByPIL(path, maxDimension)
    if HAS_SIPS:
        if imageMaxDimension(path) > maxDimension:
            print "-> shrinking " + path
            imagePath = getTempPath(path)
            subprocess.check_call([sipsTool, '--resampleHeightWidthMax', str(maxDimension), path, '--out', imagePath])
            return imagePath
    return path

def shrinkIfNeededByPIL(path, maxDimension):
    if imageMaxDimensionByPIL(path) > maxDimension:
        print "-> shrinking " + path
        imagePath = getTempPath(path)
        img = Image.open(path)
        (w,h) = img.size
        if (w>h):
            img2 = img.resize((maxDimension, (h*maxDimension)/w), Image.ANTIALIAS)
        else:
            img2 = img.resize(((w*maxDimension)/h, maxDimension), Image.ANTIALIAS)
        img2.save(imagePath, 'JPEG', quality=99)

        # now copy EXIF data from original to new
        if HAS_PYEXIV2:
            # Method 1: use PYEXIV2
            src_image = pyexiv2.ImageMetadata(path)
            src_image.read()
            dst_image = pyexiv2.ImageMetadata(imagePath)
            dst_image.read()
            src_image.copy(dst_image, exif=True)
            # overwrite image size based on new image
            dst_image["Exif.Photo.PixelXDimension"] = img2.size[0]
            dst_image["Exif.Photo.PixelYDimension"] = img2.size[1]
            dst_image.write()
        elif HAS_EXIF:
            # Method 2: use EXIFTOOL
            subprocess.call([exifTool, "-q", "-q", "-tagsfromfile", path, imagePath])
            
        return imagePath
    return path

def upload(gd_client, localPath, album, fileName, no_resize):
    print "Processing " + localPath
    contentType = getContentType(fileName)

    ##########################################################
    # Do sanity check: picture to be resized? Video file within limits?
    ##########################################################
    if contentType.startswith('image/'):
        if no_resize:
            imagePath = localPath
        else:
            imagePath = shrinkIfNeeded(localPath, PICASA_MAX_FREE_IMAGE_DIMENSION)

        isImage = True
        picasa_photo = gdata.photos.PhotoEntry()
    else:
        size = os.path.getsize(localPath)

        # tested by cpbotha on 2013-05-24
        # this limit still exists
        if size > PICASA_MAX_VIDEO_SIZE_BYTES:
            print "-> Video file too big to upload: " + str(size) + " > " + str(PICASA_MAX_VIDEO_SIZE_BYTES)
            return
        imagePath = localPath
        isImage = False
        picasa_photo = VideoEntry()
        
    ##########################################################
    # Set web metadata
    ##########################################################
    # Set title = 'filename' in the "photo details" view on Google Plus Albums     
    picasa_photo.title = atom.Title(text=fileName)      
      
    ##########################################################
    # Read EXIF/IPTC/XMP data
    ##########################################################
    print "-> reading metadata from " + imagePath

    p_summary = None
    
    # Method 1: use PYEXIV2, preferred method
    if HAS_PYEXIV2:
        p_metadata = pyexiv2.ImageMetadata(imagePath)
        p_metadata.read()
        # Retrieve DESCRIPTION
        if 'Exif.Image.ImageDescription' in p_metadata.exif_keys:
            p_summary = atom.Summary(text=p_metadata['Exif.Image.ImageDescription'].value, summary_type='text')
    
    # Method 2: use EXIFTOOL
    if ((p_summary is None) and HAS_EXIF):
        # Call ExifTool on the file to read all tags...
        exifdata = subprocess.check_output([exifTool, imagePath])
        exifdata = exifdata.splitlines()
        p_metadata = dict()
        for i, each in enumerate(exifdata):
            # tags and values are separated by a colon
            tag,val = each.split(': ', 1) # '1' only allows one split
            p_metadata[tag.strip()] = val.strip()
        
        # Now we have all tags we need in exif.keys()
        if 'Image Description' in p_metadata.keys():
            p_summary = atom.Summary(text=p_metadata['Image Description'], summary_type='text')
    
    # Add result to the to-be written picture...   
    if (p_summary is not None):              
        picasa_photo.summary = p_summary
          
    ##########################################################
    # Upload picture
    ##########################################################

    print '-> uploading ' + imagePath
    delay = 1
    while True:
        try:
            if isImage:
                photo = gd_client.InsertPhoto(album, picasa_photo, imagePath, content_type=contentType)
            else:
                video = gd_client.InsertVideo(album, picasa_photo, imagePath, content_type=contentType)
            break
        except gdata.photos.service.GooglePhotosException, e:
          print "Got exception " + str(e)
          print "retrying in " + str(delay) + " seconds"
          time.sleep(delay)
          delay = delay * 2

    # delete the temp file that was created if we shrank an image:
    if imagePath != localPath:
        os.remove(imagePath)

    ##########################################################
    # Post-processing of tags
    ########################################################## 
#    if isImage:
        #if 'Exif.Image.ImageDescription' in p_metadata.exif_keys:
            
        # Tags can be set using...
#        if not photo.media.keywords:
#            photo.media.keywords = gdata.media.Keywords()
#        photo.media.keywords.text = 'foo, bar, baz'
#        photo = gd_client.UpdatePhotoMetadata(photo)
    
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload pictures to picasa web albums / Google+.')
    parser.add_argument('--email', help='the google account email to use (example@gmail.com)', required=True)
    parser.add_argument('--password', help='the password (you will be prompted if this is omitted)', required=False)
    parser.add_argument('--source', help='the directory to upload', required=True)
    parser.add_argument(
          '--no-resize',
          help="Do not resize images, i.e., upload photos with original size.",
          action='store_true')
    parser.add_argument('--skipdirs', help='a vertical slash "|" separated list of directory regex patterns to skip', required=False)

    args = parser.parse_args()

    if args.no_resize:
        print "*** Images will be uploaded at original size."
    else:
        if (HAS_PIL_IMAGE or HAS_SIPS):
            if HAS_PIL_IMAGE:
                print "*** Images will be resized to 2048 pixels (PIL)."
            if HAS_SIPS:
                print "*** Images will be resized to 2048 pixels (SIPS)."
        else:
            print "*** WARNING: resize requested but neither PIL or SIPS has been found! Images will not be resized."
            
    email = args.email
    password = None
    if 'password' in args and args.password is not None:
        password = args.password
    else:
        password = getpass.getpass("Enter password for " + email + ": ")

    if 'skipdirs' in args and args.skipdirs is not None:
        # Get a list of all the regex's of directories to skip; we use "|" as separation character
        skipdirs = args.skipdirs.split("|")
        for regex in skipdirs:
           print '*** skipping directories: ' + regex 

    print ''
    
    gd_client = login(email, password)
    # protectWebAlbums(gd_client)
    
    # Retrieve web albums, index local albums 
    # -> Results of retrieval functions are mappings between picture path & album they correspond to
    webAlbums = getWebAlbums(gd_client)
    localAlbums = toBaseName(findMedia(args.source))
    
    # Compare albums found locally with those on the web. This will not compare individual
    # pictures but just whether the album exists or not
    albumDiff = compareLocalToWeb(localAlbums, webAlbums)
    
    # Synchronize files in albums that exist both locally & on the web
    syncDirs(gd_client, albumDiff['both'], localAlbums, webAlbums, args.no_resize)
    
    # Upload (entire) albums that exist only locally
    uploadDirs(gd_client, albumDiff['localOnly'], localAlbums, args.no_resize)

    print "*** execution finished."
    