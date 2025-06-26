CONTAINER_NAME=parse-hub-bot
docker build -t $CONTAINER_NAME .
docker rm -f $CONTAINER_NAME || true && docker run -d  --restart=always -v $PWD/logs:/app/logs --name $CONTAINER_NAME $CONTAINER_NAME
docker logs -f $CONTAINER_NAME
