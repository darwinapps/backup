import time
import os
import copy
import socket
import tempfile
import json
import sys

from fabric.api import *
from boto.s3.connection import S3Connection
from boto.s3.key import Key

with open(os.getenv('CONFIG', 'config.json')) as json_data_file:
    config = json.load(json_data_file)

TEMP_DIR = config.get('TEMP_DIR', tempfile.gettempdir())

def static_var(varname, value):
    def decorate(func):
        setattr(func, varname, value)
        return func
    return decorate

@static_var("bucket", None)
def connect():
    if connect.bucket is not None:
        return connect.bucket

    conn = S3Connection(config['AWS_ACCESS_KEY_ID'], config['AWS_SECRET_ACCESS_KEY'])

    try:
        connect.bucket = conn.get_bucket(config['AWS_BUCKET'])
    except:
        connect.bucket = conn.create_bucket(config['AWS_BUCKET'])

    return connect.bucket

def setup_archive_dir():
    env.archive_dir = '%s/%s-%s' % (config['environment'], env.prefix, time.strftime('%Y-%m-%d_%H:%M:%S'))

@task
def daily():
    env.prefix = 'daily'
    setup_archive_dir()

@task
def weekly():
    env.prefix = 'weekly'
    setup_archive_dir()

@task
def monthly():
    env.prefix = 'monthly'
    setup_archive_dir()

def cleanup():
    bucket = connect()
    result = []
    to_delete = []
    files = []
    for i in bucket.list():
        if (i.key.find("%s/%s" % (config['environment'], env.prefix)) == 0):
            result.append(os.path.dirname(i.key))
            files.append(i)

    result = list(set(result))
    result.sort()

    while len(result) > config['retain']:
        to_delete.append(result.pop(0))

    for prefix in to_delete:
        for i in files:
            if (i.key.find(prefix) == 0):
                print "Deleting %s\n" % i.key
                i.delete()

def backup_files():
    require('prefix')
    bucket = connect()
    uploads = []
    for k, v in config.get('directories', {}).iteritems():
        archive = '%s/%s.tar.gz' % (TEMP_DIR, k);
        excluded = list(map(lambda x: ("--exclude \"%s\"" % x), v.get('exclude', [])))
        local('tar -zcf %s %s -C "%s" "%s"' % (archive,  " ".join(excluded), os.path.dirname(v['root']), os.path.basename(v['root'])))
        uploads.append(archive)

    for archive in uploads:
        key = Key(bucket)
        key.key = '%s/%s' % (env.archive_dir, os.path.basename(archive))
        i = 10;
        while (i > 0):
            try:
                key.set_contents_from_filename(archive)
                local('rm %s' % archive)
                break
            except Exception, e:
                print str(e)
                print "Retrying %s\n" % key.key
                i -= 1;

def backup_mysql():
    require('prefix')
    bucket = connect()
    uploads = []
    for k, v in config.get('databases', {}).iteritems():
        v['archive'] = '%s/%s.sql.gz' % (TEMP_DIR, k)
        local('mysqldump --single-transaction --quick --net_buffer_length=10240 -u%(db_user)s -p\'%(db_password)s\' %(db_name)s | gzip > %(archive)s' % v)
        uploads.append(v['archive'])

    for archive in uploads:
        key = Key(bucket)
        key.key = '%s/%s' % (env.archive_dir, os.path.basename(archive))
        i = 10;
        while (i > 0):
            try:
                key.set_contents_from_filename(archive)
                local('rm %s' % archive)
                break
            except Exception, e:
                print str(e)
                print "Retrying %s\n" % key.key
                i -= 1;

@task
def backup():
    cleanup()
    backup_files()
    backup_mysql()
