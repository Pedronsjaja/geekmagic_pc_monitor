#!/usr/bin/env bash
set -e

echo "== GeekMagic PC Monitor - Ubuntu setup =="

sudo apt update
sudo apt install -y python3 python3-venv python3-pip lm-sensors iputils-ping

# Optional but useful: detect hardware sensors.
sudo sensors-detect --auto || true

cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f config.json ]; then
  cp config.example.json config.json
fi

echo
echo "Pronto."
echo "Edite config.json e coloque o IP do SmallTV."
echo "Depois execute: ./run_monitor.sh"
