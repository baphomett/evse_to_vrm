#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)

rm /service/$SERVICE_NAME

SUPERVISE_ID=$(pgrep -f 'supervise '"$SERVICE_NAME"'')
kill $SUPERVISE_ID

#TODO
#if SUPERVISE_ID does not exist
#echo "there was nothing to kill"
#otherwise kill


chmod a-x $SCRIPT_DIR/service/run
./restart.sh
