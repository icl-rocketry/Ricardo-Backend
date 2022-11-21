#!/bin/bash

# Get latest OSS release
sudo apt-get install -y apt-transport-https
sudo apt-get install -y software-properties-common wget
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -

# Install stable release
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install grafana


echo "Grafana has been installed"

sudo grafana-cli plugins install golioth-websocket-datasource 1.0.1

DATASOURCE_CONFIG=$(cat <<EOF
apiVersion: 1
datasources:
- name: Websockets
  type: golioth-websocket-datasource
  access: proxy
  jsonData:
    host: "ws://localhost:8080/ws"
  readOnly: false
EOF
)

echo "$DATASOURCE_CONFIG" | sudo tee /etc/grafana/provisioning/datasources/ws.yaml 
echo "Golioth setup complete"

# Start the Grafana server
sudo systemctl daemon-reload
sudo systemctl start grafana-server
sudo systemctl status grafana-server

# Always start Grafana server at boot
sudo systemctl enable grafana-server.service

echo "Grafana server started"