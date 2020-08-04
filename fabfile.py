import time
import os
import copy
import socket
import tempfile
import json
import pipes
import boto
import sys
import paramiko

from scp import SCPClient
from datetime import datetime
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
    # env.archive_dir = '%s/%s-%s' % (config['environment'], env.prefix, time.strftime('%Y-%m-%d_%H:%M:%S'))
    # env.archive_dir = '%s/%s-%s' % (env.prefix, env.prefix, time.strftime('%Y-%m-%d_%H:%M:%S'))
    env.archive_dir = '%s/%s/%s-%s' % (config['environment'], env.prefix, env.prefix, time.strftime('%Y-%m-%d_%H:%M:%S'))


@task
def custom():
    env.prefix = 'custom'
    setup_archive_dir()
    
@task
def hourly():
    global retain
    retain = config['retain']['hourly']

    env.prefix = 'hourly'
    setup_archive_dir()
    
@task
def daily():
    global retain
    retain = config['retain']['daily']

    env.prefix = 'daily'
    setup_archive_dir()

@task
def weekly():
    global retain
    retain = config['retain']['weekly']

    env.prefix = 'weekly'
    setup_archive_dir()

@task
def monthly():
    global retain
    retain = config['retain']['monthly']

    env.prefix = 'monthly'
    setup_archive_dir()

def cleanup():
    bucket = connect()
    result = []
    to_delete = []
    files = []
    for i in bucket.list():
        if (i.key.find("%s/%s/%s" % (config['environment'], env.prefix, env.prefix)) == 0):
            result.append(os.path.dirname(i.key))
            files.append(i)

    result = list(set(result))
    result.sort()

    while len(result) > retain:
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
    # if config.get('retain', 0):
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
        # if config.get('retain', 0) or v.get('alias'):
        
        _v = copy.copy(v);
        _v['archive'] = '%s/%s.sql.gz' % (TEMP_DIR, k)
        _v['db_password'] = pipes.quote(_v['db_password'])

        if v.get('docker_container'):
            local('docker exec %(docker_container)s /usr/bin/mysqldump --single-transaction --quick --net_buffer_length=10240 -u%(db_user)s -p%(db_password)s %(db_name)s | gzip > %(archive)s' % _v)
        else:
            local('mysqldump --single-transaction --quick --net_buffer_length=10240 -u%(db_user)s -p%(db_password)s %(db_name)s | gzip > %(archive)s' % _v)

        # if config.get('retain', 0):
        key = Key(bucket)
        key.key = '%s/%s' % (env.archive_dir, os.path.basename(_v['archive']))
        s3_upload(key, _v['archive'])

        if v.get('alias'):
            key = Key(bucket)
            key.key = _v.get('alias')
            s3_upload(key, _v['archive'])

        local('rm "%s"' % _v['archive'])



def put_db_files_to_aws():
    require('prefix')
    bucket = connect()
    uploads = []

    db_file = 'application.sql.gz';
    site_file = 'files.tgz';

    key = Key(bucket)
    key.key = '%s/%s' % (env.archive_dir, os.path.basename(db_file))
    s3_upload(key, db_file)
    
    key = Key(bucket)
    key.key = 'latest.sql.gz'
    s3_upload(key, db_file)

    print('%s : MySQL DB downloaded to AWS') % (DateNow())


    key = Key(bucket)
    key.key = '%s/%s' % (env.archive_dir, os.path.basename(site_file))
    s3_upload(key, site_file)

    print('%s : Site\'s files downloaded to AWS') % (DateNow())

    local('rm "%s"' % db_file)
    local('rm "%s"' % site_file)
                

def get_latest_db_via_ssh():
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname=ssh_host,
                    username=ssh_username,
                    password=ssh_password,
                    port=int(ssh_port))
    except:
        print("!!! Errors !!!")
        print("The connection is not established!")
        exit(1)


    cmdssh =    'mysqldump -u'+mysql_username+\
                ' -p'+mysql_password+\
                ' -h'+mysql_host+\
                ' -P'+mysql_port+\
                ' '+mysql_base+\
                '| gzip > application.sql.gz'

    print('%s : Dump MySQL DB started ...') % (DateNow())
    
    stdin, stdout, stderr = ssh.exec_command(cmdssh)
    
    OutData = stdout.read()
    if OutData :
        print(OutData)

    ErrData = stderr.read()
    if ErrData :
        print( "!!! Errors !!!")
        print(ErrData)
        exit(1)
    
    
    print('%s : Dump MySQL DB was created') % (DateNow())
    

    scp = SCPClient(ssh.get_transport())
    scp.get('application.sql.gz')
    scp.close()

    cmdssh = 'rm -f application.sql.gz'
    ssh.exec_command(cmdssh)
    
    ssh.close()

    print("%s : MySQL DB downloaded via SSH")  % (DateNow())



def get_latest_files_dump_via_ssh():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname=ssh_host,
                    username=ssh_username,
                    password=ssh_password,
                    port=int(ssh_port))
    except:
        print("!!! Errors !!!")
        print("The connection is not established!")
        exit(1)

    cmdssh = 'tar -zcPf files.tgz %s --exclude=\".git\"' % (files_path)
    
    print('%s : Site\'s files compression started ...') % (DateNow())
    
    stdin, stdout, stderr = ssh.exec_command(cmdssh)
    
    OutData = stdout.read()
    if OutData :
        print(OutData)

    ErrData = stderr.read()
    if ErrData :
        print( "!!! Errors !!!")
        print(ErrData)
        exit(1)
    
    print('%s : Site\'s files was compressed') % (DateNow())
    print('%s : Site\'s files download started ...') % (DateNow())

    scp = SCPClient(ssh.get_transport())
    scp.get('files.tgz')
    scp.close()

    cmdssh = 'rm -f files.tgz'
    ssh.exec_command(cmdssh)
    
    ssh.close()

    print("%s : Site\'s files downloaded via SSH") % (DateNow())


def DateNow():
    return datetime.now().strftime("%d-%b-%Y (%H:%M:%S)")


def split_data():
    global files_path
    global ssh_username, ssh_password, ssh_port, ssh_host
    global mysql_username, mysql_password, mysql_host, mysql_port, mysql_base

    files_path = config.get('FILES_PATH')

    generic_ssh = config.get('GENERIC_SSH').split('@')
    ssh_username, ssh_password      = generic_ssh[0].split(':')
    ssh_host, ssh_port              = generic_ssh[1].split(':')

    remote_mysql = config.get('REMOTE_MYSQL').split('@')
    mysql_username, mysql_password  = remote_mysql[0].split(':')
    mysql_host, mysql_portbase      = remote_mysql[1].split(':')
    mysql_port, mysql_base          = mysql_portbase.split('/')
    

@task
def backup():
    backup_files()
    backup_mysql()
    cleanup()


@task
def backup_via_ssh_to_aws():
    print('%s : Start %s backup DB and Files via SSH to AWS') % (DateNow(),env.prefix)
    split_data()
    get_latest_db_via_ssh()
    get_latest_files_dump_via_ssh()
    put_db_files_to_aws()
    cleanup()
