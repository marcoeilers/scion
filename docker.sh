#!/bin/bash

branch=
build_dir=
image_tag=

get_params() {
  # If we're on a local branch, use that. If we're on a detached HEAD from a
  # remote branch, or from a bare rev id, use that instead.
  branch=$(git status | head -n1 |
           awk '/^On branch|HEAD detached at/ {print $NF}')
  build_dir="docker/_build/$branch"
  image_tag=$(echo "$branch" | tr '/' '.')
}

cmd_build() {
    set -e
    set -o pipefail
    make -s go
    get_params
    echo
    echo "Copying current working tree for Docker image"
    echo "============================================="
    mkdir -p "${build_dir:?}"
    # Just in case it's sitting there from a previous run
    rm -rf "${build_dir}/scion.git/"
    {
        git ls-files;
        git submodule --quiet foreach 'git ls-files | sed "s|^|$path/|"';
    } | rsync -a --files-from=- . "${build_dir}/scion.git/"
    cp bin/border bin/discovery "${build_dir}/scion.git/bin"
    # Needed so that the go.capnp references in proto/*.capnp don't break
    cp proto/go.capnp "${build_dir}/scion.git/proto"
    echo
    echo "Building Docker image"
    echo "====================="
    docker_build "build.log"
}

docker_build() {
    set -e
    set -o pipefail
    local log_file="$1"; shift
    local image_name="scion"
    local args=""
    echo "Image: $image_name:$image_tag"
    echo "Log: $build_dir/$log_file"
    echo "============================"
    echo
    if [ -n "$CIRCLECI" ]; then
        # We're running on CircleCI, so don't rm images and *do* use -f during tagging
        docker build --rm=false -t "${image_name:?}:${image_tag:?}" "${build_dir:?}/scion.git" |
            tee "$build_dir/${log_file:?}"
        docker tag -f "$image_name:$image_tag" "$image_name:latest"
    else
        docker build $args -t "${image_name:?}:${image_tag:?}" "${build_dir:?}/scion.git" |
            tee "$build_dir/${log_file:?}"
        docker tag "$image_name:$image_tag" "$image_name:latest"
    fi
}

cmd_clean() {
    stop_cntrs
    del_cntrs
    del_imgs
    rm -rf docker/_build/
}

cmd_run() {
    local args="-i -t --privileged -h scion"
    args+=" -v $PWD/htmlcov:/home/scion/go/src/github.com/netsec-ethz/scion/htmlcov"
    args+=" -v $PWD/logs:/home/scion/go/src/github.com/netsec-ethz/scion/logs"
    args+=" -v $PWD/sphinx-doc/_build:/home/scion/go/src/github.com/netsec-ethz/scion/sphinx-doc/_build"
    # Can't use --rm in circleci, their environment doesn't allow it, so it
    # just throws an error
    [ -n "$CIRCLECI" ] || args+=" --rm"
    setup_volumes
    docker run $args scion "$@"
}

setup_volumes() {
    set -e
    for i in htmlcov logs sphinx-doc/_build; do
        mkdir -p "$i"
        # Check dir exists, and is owned by the current (effective) user. If
        # it's owned by the wrong user, the docker environment won't be able to
        # write to it.
        [ -O "$i" ] || { echo "Error: '$i' dir not owned by $LOGNAME"; exit 1; }
    done
}

stop_cntrs() {
    local running
    running=$(docker ps -q)
    if [ -n "$running" ]; then
        echo
        echo "Stopping running containers"
        echo "==========================="
        docker stop $running
    fi
}

del_cntrs() {
    local stopped
    stopped=$(docker ps -aq)
    if [ -n "$stopped" ]; then
        echo
        echo "Deleting stopped containers"
        echo "==========================="
        docker rm $stopped
    fi
}

del_imgs() {
    local images
    images=$(docker images | awk '/^scion/ {print $1":"$2}; /^<none>/ {print $3}')
    if [ -n "$images" ]; then
        echo
        echo "Deleting all generated images"
        echo "============================="
        docker rmi $images
    fi
}

cmd_help() {
	cat <<-_EOF
	Usage:
	    $PROGRAM build
	    $PROGRAM run
	        Run the Docker image.
	    $PROGRAM clean
	        Remove all Docker containers and all generated images.
	    $PROGRAM help
	        Show this text.
	_EOF
}


PROGRAM="${0##*/}"
COMMAND="$1"
ARG="$2"

if ! ( [ $(id -u) -eq 0 ] || groups | grep -q "\<docker\>"; ); then
    echo "Error: you must either be root, or in the 'docker' group"
    exit 1
fi

if ! type -p docker &>/dev/null; then
    echo "Error: you don't have docker installed. Please see docker/README.md"
    exit 1
fi

case $COMMAND in
    build)              cmd_build ;;
    clean)              cmd_clean ;;
    run)                shift; cmd_run "$@" ;;
    help)               cmd_help ;;
    *)                  cmd_help ;;
esac
