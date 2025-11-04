#!/bin/bash

CONTAINER_NAME=parse-hub-bot

# 构建镜像
build_image() {
    echo "正在构建镜像..."
    docker build -t $CONTAINER_NAME .
    echo "镜像构建成功！"
}

# 启动容器
start_container() {
    echo "正在启动容器..."
    docker run -d --restart=on-failure:2 --env-file .env -v $PWD/logs:/app/logs -v $PWD/platform_config.yaml:/app/platform_config.yaml --name $CONTAINER_NAME $CONTAINER_NAME
    echo "容器启动成功！"
    show_logs
}

# 构建&启动容器
build_and_start_container() {
    build_image
    stop_container
    start_container
}

# 停止容器
stop_container() {
    echo "正在停止容器..."
    docker stop $CONTAINER_NAME || true
    docker rm -f $CONTAINER_NAME || true
    echo "容器已停止并移除！"
}

# 重启容器
restart_container() {
    echo "正在重启容器..."
    stop_container
    start_container
    echo "容器重启成功！"
}

# 查看日志
show_logs() {
    echo "显示容器日志..."
    docker logs -f $CONTAINER_NAME
}

# 查看容器状态
show_status() {
    echo "容器状态："
    docker ps -a --filter "name=$CONTAINER_NAME"
}

# 显示帮助信息
show_help() {
    echo "用法: $0 [命令]"
    echo ""
    echo "可用命令:"
    echo "  start     构建&启动"
    echo "  stop      停止"
    echo "  restart   重启"
    echo "  logs      查看日志"
    echo "  status    查看状态"
    echo "  help      显示此帮助信息"
    echo ""
    echo "如果不提供命令，默认执行 start 操作"
}

# 主逻辑
case "${1:-start}" in
    start)
        build_and_start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "错误: 未知命令 '$1'"
        echo ""
        show_help
        exit 1
        ;;
esac