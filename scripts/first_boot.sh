#!/bin/bash

echo "________Start of first_boot.sh________"

BOOT_COUNT_RESPONSE=$(curl -sk http://bootcount:8082/api/count/)
BOOT_COUNT=$(echo $BOOT_COUNT_RESPONSE | jq --raw-output '.count')

if [[ $BOOT_COUNT == "1" ]]; then
  # Restart the container
  echo "This is the first boot, so restarting the interactive label container in 30 seconds to resolve the background image turning black..."
  sleep 30
  # Update the boot count
  curl --request POST 'http://bootcount:8082/api/count/'
  # Restart the interactive label container
  curl -H "Content-Type: application/json" -d "{\"serviceName\": \"$BALENA_SERVICE_NAME\"}" "$BALENA_SUPERVISOR_ADDRESS/v2/applications/$BALENA_APP_ID/restart-service?apikey=$BALENA_SUPERVISOR_API_KEY"
else
  echo "Boot count is $BOOT_COUNT so not restarting..."
fi

echo "________End of first_boot.sh________"
