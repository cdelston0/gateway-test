#!/bin/bash

START=10
END=200
CHANGES=10
HOST="127.0.0.1:8080"
TESTCASE=test_2_property_change_via_POST_no_wait_for_gateway
USER=testuser@email.com
PASS=testpass

for things in `seq ${START} 10 ${END}`; do
	echo "${TESTCASE} ${things} things ${CHANGES} changes"
	taskset 0xF7 python3 test.py --gateway-url=http://${HOST} --gateway-user=${USER} \
		--gateway-password=${PASS} --things-quantity=${things} --property-changes=${CHANGES} \
		MultipleThingProfiling.${TESTCASE} | tee testlog_${things}_${CHANGES}.log 2>&1
done
