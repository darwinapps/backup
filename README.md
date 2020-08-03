This script **fabfile.py** allows to create backups of MySQL databases and files and copy to AWS S3. Database and files may be located locally or remotely (access via SSH). Also, database may been running in docker container.

## **Examples**

------

### Backup to AWS via SSH

**run:**

```
fab -f fabfile.py daily backup_via_ssh_to_aws
```

**config.json**

```
{
    "GENERIC_SSH": "user_ssh:pass_ssh@ip_ssh:port_ssh",
    "REMOTE_MYSQL": "user_mysql:pass_mysql@localhost:3306/db_mysql",
    "FILES_PATH": "/file_path/for/backup",

    "AWS_ACCESS_KEY_ID": "aws_key_id",
    "AWS_SECRET_ACCESS_KEY": "aws_access_key",
    "AWS_BUCKET": "aws_bucket",
    "AWS_REGION": "us-east-1",
    "environment": "production",
    "retain": {
        "hourly": 4,
        "daily": 7,
        "weekly": 8,
        "monthly": 12
    }
}
```



### Backup locally to AWS

**run:**

```
fab -f fabfile.py daily backup
```

**config.json**

```
{
    "AWS_ACCESS_KEY_ID": "aws_key_id",
    "AWS_SECRET_ACCESS_KEY": "aws_access_key",
    "AWS_BUCKET": "aws_bucket",
    "AWS_REGION": "us-east-1",
    "environment": "production",
    "retain": {
        "hourly": 4,
        "daily": 7,
        "weekly": 8,
        "monthly": 12
    },


    "directories": {
        "application": {
            "root": "/file_path/for/backup",
            "exclude": [
                 ".git"
            ]
        }
    },


    "databases": {
        "application": {
            "docker_container": "docker-container-mysql",  // This setting is necessary if MySQL is running in docker
            "db_name": "db_mysql",
            "db_user": "user_mysql",
            "db_password": "pass_mysql",
            "alias": "latest.sql.gz"
        }
    }
}
```



## Backing up

```
$ ID=$(docker build . -q) && docker run --rm -it -w /app -v "$PWD:/app" -v "/var/www/html:/var/www/html" $ID fab daily backup
$ ID=$(docker build . -q) && docker run --rm -it -w /app -v "$PWD:/app" -e CONFIG=alternate.json -v "/var/www/html:/var/www/html" $ID fab daily backup
```
