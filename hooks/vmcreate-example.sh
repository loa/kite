#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

date >> $DIR/../test.log
printenv >> $DIR/../test.log
echo >> $DIR/../test.log

