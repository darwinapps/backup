## Backing up

```
$ ID=$(docker build . -q) && docker run --rm -it -w /app -v "$PWD:/app" -v "/var/www/html:/var/www/html" $ID fab daily backup
$ ID=$(docker build . -q) && docker run --rm -it -w /app -v "$PWD:/app" -e CONFIG=alternate.json -v "/var/www/html:/var/www/html" $ID fab daily backup
```
