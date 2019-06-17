import time
import os
import copy
import socket
import tempfile
import json
import pipes
import boto

from fabric.api import *
from boto.s3.connection import OrdinaryCallingFormat
from boto.s3.key import Key

path = os.path.dirname(os.path.realpath(__file__))
with open(os.getenv('CONFIG', path + '/config.json')) as json_data_file:
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

    conn = boto.s3.connect_to_region(
         config['AWS_REGION'],
         aws_access_key_id=config['AWS_ACCESS_KEY_ID'],
         aws_secret_access_key=config['AWS_SECRET_ACCESS_KEY'],
         calling_format=OrdinaryCallingFormat()
    )
    connect.bucket = conn.get_bucket(config['AWS_BUCKET'])
    return connect.bucket

def setup_archive_dir():
    env.archive_dir = '%s/%s-%s' % (config['environment'], env.prefix, time.strftime('%Y-%m-%d_%H:%M:%S'))

@task
def custom():
    env.prefix = 'custom'
    setup_archive_dir()
    
@task
def hourly():
    env.prefix = 'hourly'
    setup_archive_dir()
    
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

def s3_upload(key, filename, retries = 3):
    while (retries > 0):
        try:
            key.set_contents_from_filename(filename)
            break
        except Exception, e:
            print str(e)
            print "Retrying %s\n" % key.key
            retries -= 1;

def backup_files():
    require('prefix')
    bucket = connect()
    uploads = []
    if config.get('retain', 0):
        for k, v in config.get('directories', {}).iteritems():
            archive = '%s/%s.tar.gz' % (TEMP_DIR, k);
            excluded = list(map(lambda x: ("--exclude \"%s\"" % x), v.get('exclude', [])))
            local('tar -zcf %s %s -C "%s" "%s"' % (archive,  " ".join(excluded), os.path.dirname(v['root']), os.path.basename(v['root'])))
            key = Key(bucket)
            key.key = '%s/%s' % (env.archive_dir, os.path.basename(archive))
            s3_upload(key, archive)
            local('rm "%s"' % archive)

def backup_mysql():
    require('prefix')
    bucket = connect()
    uploads = []
    for k, v in config.get('databases', {}).iteritems():
        if config.get('retain', 0) or v.get('alias'):
            _v = copy.copy(v);
            _v['archive'] = '%s/%s.sql.gz' % (TEMP_DIR, k)
            _v['db_password'] = pipes.quote(_v['db_password'])
            local('mysqldump --single-transaction --quick --net_buffer_length=10240 -u%(db_user)s -p%(db_password)s %(db_name)s | gzip > %(archive)s' % _v)

            if config.get('retain', 0):
                key = Key(bucket)
                key.key = '%s/%s' % (env.archive_dir, os.path.basename(_v['archive']))
                s3_upload(key, _v['archive'])

            if v.get('alias'):
                key = Key(bucket)
                key.key = _v.get('alias')
                s3_upload(key, _v['archive'])

            local('rm "%s"' % _v['archive'])

@task
def backup():
    backup_files()
    backup_mysql()
    cleanup()
