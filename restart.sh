#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)

PROC_ID=$(pgrep -f $SCRIPT_DIR/$SERVICE_NAME.py)
kill $PROC_ID

#TODO
#if PROC_ID does not exist
#echo "there was nothing to kill"
#otherwise kill

